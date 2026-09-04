from django import forms


class CheckoutForm(forms.Form):

    PAYMENT_METHOD_CHOICES = [
        ('bkash', 'bKash'),
        ('nagad', 'Nagad'),
        ('bank', 'Bank / Card'),
    ]

    recipient_name = forms.CharField(
        max_length=150
    )

    email = forms.EmailField()

    phone_number = forms.CharField(
        max_length=15
    )

    delivery_address = forms.CharField(
        widget=forms.Textarea(
            attrs={
                'rows': 4,
                'placeholder': 'Enter delivery address'
            }
        )
    )

    payment_method = forms.ChoiceField(
        choices=PAYMENT_METHOD_CHOICES
    )