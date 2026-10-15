from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from agro_updates.models import Video
from bidding.models import Auction
from disputes.models import Dispute
from disputes.services import FINAL_DISPUTE_STATUSES, decide_dispute
from orders.models import Order
from payments.models import Payment
from payments.services import COMMISSION_RATE, OPEN_DISPUTE_STATUSES, fail_payment, verify_payment
from products.models import Product
from .audit import DecisionError
from .forms import ActionForm, DisputeDecisionForm
from .models import AuditRecord
from .permissions import CATALOGUE, FINANCE, SUPPORT, has_role, staff_role_required
from .services import review_product, review_seller

User = get_user_model()
PAYMENT_TABS = [
    ('verification_pending', 'Needs verification'), ('paid', 'Paid'), ('failed', 'Failed'),
    ('refunded', 'Refunded'), ('pending', 'Awaiting buyer'),
]
STALE_HOURS = {'payments': 48, 'disputes': 72, 'products': 72, 'sellers': 72}


def cutoff(queue):
    hours = getattr(settings, 'DASHBOARD_STALE_HOURS', {}).get(queue, STALE_HOURS[queue])
    return timezone.now() - timedelta(hours=hours)


def queues():
    return {
        'payments': Payment.objects.filter(payment_status='verification_pending'),
        'disputes': Dispute.objects.filter(status__in=OPEN_DISPUTE_STATUSES),
        'products': Product.objects.filter(verification_status='pending'),
        'sellers': User.objects.filter(seller_requested=True, seller_approved=False),
    }


def page(request, queryset, size=25, param='page'):
    return Paginator(queryset, size).get_page(request.GET.get(param))


def panel(request, template, title, section, **context):
    context.update(
        title=title, section=section, agro_draft_count=Video.objects.filter(is_published=False).count(),
        can_finance=has_role(request.user, FINANCE), can_support=has_role(request.user, SUPPORT),
        can_catalogue=has_role(request.user, CATALOGUE),
        queue_sizes={key: value.count() for key, value in queues().items()},
    )
    return render(request, f'dashboard/{template}.html', context)


def tab_filter(request, queryset, choices, field, default):
    selected = request.GET.get('tab', default)
    if selected not in dict(choices):
        selected = default
    counts = dict(queryset.values(field).annotate(count=Count('pk')).values_list(field, 'count'))
    tabs = [{'value': key, 'label': label, 'count': counts.get(key, 0)} for key, label in choices]
    return queryset.filter(**{field: selected}), selected, tabs


@staff_role_required()
@require_GET
def overview(request):
    waiting = queues()
    overdue_fields = {'payments': 'updated_at', 'disputes': 'created_at',
                      'products': 'created_at', 'sellers': 'seller_requested_at'}
    role_by_queue = {'payments': FINANCE, 'disputes': SUPPORT, 'products': CATALOGUE, 'sellers': CATALOGUE}
    aged = [{'label': name.title(), 'count': qs.filter(**{overdue_fields[name] + '__lt': cutoff(name)}).count(),
             'hours': getattr(settings, 'DASHBOARD_STALE_HOURS', {}).get(name, STALE_HOURS[name]),
             'url_name': f'dashboard:{name}', 'allowed': has_role(request.user, role_by_queue[name])}
            for name, qs in waiting.items()]
    money = Payment.objects.aggregate(
        held=Sum('amount', filter=Q(payment_status='paid', escrow_status='held')),
        released=Sum('seller_amount', filter=Q(escrow_status='released')),
        commission=Sum('commission_amount', filter=Q(escrow_status='released')),
        refunded=Sum('amount', filter=Q(payment_status='refunded', escrow_status='refunded')),
    )
    now = timezone.now()
    running = Auction.objects.filter(status__in=('upcoming', 'active'), start_time__lte=now, end_time__gt=now)
    status_counts = dict(Order.objects.values('status').annotate(count=Count('pk')).values_list('status', 'count'))
    return panel(request, 'overview', 'Overview', 'overview',
                 money={key: value or Decimal('0.00') for key, value in money.items()},
                 order_statuses=[(label, status_counts.get(key, 0)) for key, label in Order.STATUS_CHOICES],
                 running_auctions=running.count(), ending_auctions=running.filter(end_time__lte=now + timedelta(hours=24)).count(),
                 overdue=aged,
                 page_obj=page(request, AuditRecord.objects.filter(Q(actor__is_staff=True) | Q(actor__is_superuser=True)).select_related('actor'), size=10))


@staff_role_required(FINANCE)
@require_GET
def payments(request):
    qs, selected, tabs = tab_filter(request, Payment.objects.select_related('order__buyer', 'order__seller'),
                                    PAYMENT_TABS, 'payment_status', 'verification_pending')
    overdue = request.GET.get('overdue') == '1'
    if overdue:
        qs = qs.filter(payment_status='verification_pending', updated_at__lt=cutoff('payments'))
    return panel(request, 'payments', 'Payments', 'payments', page_obj=page(request, qs.order_by('updated_at', 'pk')),
                 selected=selected, tabs=tabs, overdue=overdue)


def perform(request, service, pk, destination, **kwargs):
    form = ActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'The note must be at most 4,000 characters.')
    else:
        try:
            service(pk, actor=request.user, note=form.cleaned_data['note'], **kwargs)
        except DecisionError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, 'Decision saved and recorded in the activity log.')
    return redirect(destination)


@staff_role_required(FINANCE)
@require_POST
def payment_verify(request, pk):
    get_object_or_404(Payment, pk=pk)
    return perform(request, verify_payment, pk, 'dashboard:payments')


@staff_role_required(FINANCE)
@require_POST
def payment_fail(request, pk):
    get_object_or_404(Payment, pk=pk)
    return perform(request, fail_payment, pk, 'dashboard:payments')


@staff_role_required(SUPPORT)
@require_GET
def disputes(request):
    qs = Dispute.objects.select_related('order__buyer', 'order__seller')
    selected = request.GET.get('tab', 'open')
    choices = [('open', 'Open cases'), ('under_review', 'Under review'), ('refund_approved', 'Refunded'),
               ('seller_favored', 'Seller favoured'), ('rejected', 'Rejected')]
    if selected not in dict(choices):
        selected = 'open'
    filters = {key: Q(status=key) for key, _ in choices}
    filters['open'] = Q(status__in=OPEN_DISPUTE_STATUSES)
    tabs = [{'value': key, 'label': label, 'count': qs.filter(filters[key]).count()} for key, label in choices]
    qs = qs.filter(filters[selected])
    overdue = request.GET.get('overdue') == '1'
    if overdue:
        qs = qs.filter(status__in=OPEN_DISPUTE_STATUSES, created_at__lt=cutoff('disputes'))
    return panel(request, 'disputes', 'Disputes', 'disputes', page_obj=page(request, qs.order_by('created_at', 'pk')),
                 selected=selected, tabs=tabs, overdue=overdue)


def dispute_context(request, dispute, form, status=200):
    response = panel(request, 'dispute_detail', f'Dispute #{dispute.pk}', 'disputes', dispute=dispute,
                     payment=Payment.objects.filter(order=dispute.order).first(), form=form,
                     commission_percent=COMMISSION_RATE * 100,
                     resolved=dispute.status in FINAL_DISPUTE_STATUSES or bool(dispute.resolved_at))
    response.status_code = status
    return response


@staff_role_required(SUPPORT)
@require_GET
def dispute_detail(request, pk):
    dispute = get_object_or_404(Dispute.objects.select_related('order__buyer', 'order__seller', 'resolved_by'), pk=pk)
    return dispute_context(request, dispute, DisputeDecisionForm())


@staff_role_required(SUPPORT)
@require_POST
def dispute_decide(request, pk):
    dispute = get_object_or_404(Dispute.objects.select_related('order__buyer', 'order__seller', 'resolved_by'), pk=pk)
    form = DisputeDecisionForm(request.POST)
    if not form.is_valid():
        return dispute_context(request, dispute, form, status=400)
    try:
        decide_dispute(pk, actor=request.user, **form.cleaned_data)
    except DecisionError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, 'Dispute decision saved and audited.')
    return redirect('dashboard:dispute_detail', pk=pk)


@staff_role_required(CATALOGUE)
@require_GET
def products(request):
    qs, selected, tabs = tab_filter(request, Product.objects.select_related('seller'),
                                    Product.VERIFICATION_STATUS_CHOICES, 'verification_status', 'pending')
    overdue = request.GET.get('overdue') == '1'
    if overdue:
        qs = qs.filter(verification_status='pending', created_at__lt=cutoff('products'))
    return panel(request, 'products', 'Products', 'products', page_obj=page(request, qs.order_by('created_at', 'pk')),
                 selected=selected, tabs=tabs, overdue=overdue)


@staff_role_required(CATALOGUE)
@require_POST
def product_decide(request, pk, decision):
    get_object_or_404(Product, pk=pk)
    return perform(request, review_product, pk, 'dashboard:products', decision=decision)


@staff_role_required(CATALOGUE)
@require_GET
def sellers(request):
    selected = request.GET.get('tab', 'requests')
    if selected not in ('requests', 'approved'):
        selected = 'requests'
    requests = User.objects.filter(seller_requested=True, seller_approved=False)
    approved = User.objects.filter(seller_approved=True)
    tabs = [{'value': 'requests', 'label': 'Requests', 'count': requests.count()},
            {'value': 'approved', 'label': 'Approved sellers', 'count': approved.count()}]
    qs = requests if selected == 'requests' else approved
    overdue = request.GET.get('overdue') == '1'
    if overdue:
        qs = qs.filter(seller_requested=True, seller_approved=False, seller_requested_at__lt=cutoff('sellers'))
    return panel(request, 'sellers', 'Sellers', 'sellers', page_obj=page(request, qs.order_by('seller_requested_at', 'pk')),
                 selected=selected, tabs=tabs, overdue=overdue)


@staff_role_required(CATALOGUE)
@require_POST
def seller_decide(request, pk, decision):
    get_object_or_404(User, pk=pk)
    return perform(request, review_seller, pk, 'dashboard:sellers', decision=decision)


@staff_role_required()
@require_GET
def orders(request):
    qs = Order.objects.select_related('buyer', 'seller')
    search = request.GET.get('q', '').strip()[:150]
    status = request.GET.get('status', '')
    if search:
        query = Q(buyer__username__icontains=search) | Q(seller__username__icontains=search)
        query |= Q(buyer__email__icontains=search) | Q(seller__email__icontains=search)
        number = search.removeprefix('#')
        if number.isascii() and number.isdigit() and len(number) < 19:
            query |= Q(pk=int(number))
        qs = qs.filter(query)
    if status in dict(Order.STATUS_CHOICES):
        qs = qs.filter(status=status)
    else:
        status = ''
    return panel(request, 'orders', 'Orders', 'orders', page_obj=page(request, qs.order_by('-created_at', '-pk')),
                 search=search, selected_status=status, statuses=Order.STATUS_CHOICES)


@staff_role_required()
@require_GET
def activity(request):
    return panel(request, 'activity', 'Activity log', 'activity',
                 page_obj=page(request, AuditRecord.objects.select_related('actor')))
