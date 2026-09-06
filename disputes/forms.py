from django import forms

from .models import Dispute


class DisputeForm(forms.ModelForm):

    class Meta:
        model = Dispute
        fields = [
            'reason',
            'description',
        ]

        widgets = {
            'description': forms.Textarea(
                attrs={
                    'rows': 5,
                    'placeholder': 'Describe the problem with your order...'
                }
            )
        }


class SellerResponseForm(forms.ModelForm):

    class Meta:
        model = Dispute
        fields = [
            'seller_response',
        ]

        widgets = {
            'seller_response': forms.Textarea(
                attrs={
                    'rows': 5,
                    'placeholder': 'Write your response to the buyer complaint...'
                }
            )
        }