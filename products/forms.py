from django import forms
from .models import Product


class ProductForm(forms.ModelForm):

    class Meta:
        model = Product
        fields = '__all__'

        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full p-3 border border-gray-300 rounded-lg'
            }),

            'description': forms.Textarea(attrs={
                'class': 'w-full p-3 border border-gray-300 rounded-lg'
            }),

            'category': forms.TextInput(attrs={
                'class': 'w-full p-3 border border-gray-300 rounded-lg'
            }),

            'price': forms.NumberInput(attrs={
                'class': 'w-full p-3 border border-gray-300 rounded-lg'
            }),

            'stock_quantity': forms.NumberInput(attrs={
                'class': 'w-full p-3 border border-gray-300 rounded-lg'
            }),
        }