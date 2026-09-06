from django import forms

from .models import Auction, Bid


class AuctionForm(forms.ModelForm):

    class Meta:
        model = Auction
        fields = [
            'starting_price',
            'minimum_increment',
            'start_time',
            'end_time',
        ]

        widgets = {
            'start_time': forms.DateTimeInput(
                attrs={'type': 'datetime-local'}
            ),
            'end_time': forms.DateTimeInput(
                attrs={'type': 'datetime-local'}
            ),
        }

    def clean(self):
        cleaned_data = super().clean()

        starting_price = cleaned_data.get('starting_price')
        minimum_increment = cleaned_data.get('minimum_increment')
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')

        if starting_price is not None and starting_price <= 0:
            self.add_error(
                'starting_price',
                'Starting price must be greater than 0.'
            )

        if minimum_increment is not None and minimum_increment <= 0:
            self.add_error(
                'minimum_increment',
                'Minimum increment must be greater than 0.'
            )

        if start_time and end_time:
            if end_time <= start_time:
                self.add_error(
                    'end_time',
                    'End time must be after start time.'
                )

        return cleaned_data


class BidForm(forms.ModelForm):

    class Meta:
        model = Bid
        fields = ['amount']

    def __init__(self, *args, auction=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.auction = auction

    def clean_amount(self):
        amount = self.cleaned_data['amount']

        if not self.auction:
            return amount

        highest_bid = self.auction.bids.order_by(
            '-amount'
        ).first()

        if highest_bid:
            minimum_bid = (
                highest_bid.amount
                + self.auction.minimum_increment
            )
        else:
            minimum_bid = self.auction.starting_price

        if amount < minimum_bid:
            raise forms.ValidationError(
                f'Minimum bid is ৳{minimum_bid}.'
            )

        return amount