from django import forms


class ActionForm(forms.Form):
    note = forms.CharField(required=False, max_length=4000, widget=forms.Textarea(attrs={'rows': 3}))


class DisputeDecisionForm(ActionForm):
    decision = forms.ChoiceField(choices=[
        ('under_review', 'Mark under review'),
        ('refund_approved', 'Refund buyer and cancel order'),
        ('seller_favored', 'Favour seller and release escrow'),
        ('rejected', 'Reject dispute and release escrow'),
    ])
