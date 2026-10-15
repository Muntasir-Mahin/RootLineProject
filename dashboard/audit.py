from .models import AuditRecord


class DecisionError(ValueError):
    """A transition is invalid; safe to show to the person making the decision."""


def record_action(*, actor, action, target, summary, note=''):
    if not actor or not actor.is_authenticated or not actor.pk:
        raise DecisionError('An authenticated actor is required.')
    return AuditRecord.objects.create(
        actor=actor, actor_name=actor.get_username(), action=action,
        target=f'{target._meta.label_lower}:{target.pk}', summary=summary, note=note,
    )
