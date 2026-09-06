from django import forms


class PaymentForm(forms.Form):
    transaction_id = forms.CharField(
        max_length=100,
        label='Transaction ID'
    )