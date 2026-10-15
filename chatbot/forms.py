from django import forms
from .images import DEFAULT_IMAGE_QUESTION, prepare_image


class QuestionForm(forms.Form):
    message = forms.CharField(max_length=2000, strip=True, required=False, label='Your question')
    image = forms.FileField(required=False)

    def clean_image(self):
        image = self.cleaned_data.get('image')
        return prepare_image(image) if image else None

    def clean(self):
        data = super().clean()
        if not data.get('message') and not data.get('image'):
            raise forms.ValidationError('Type a question first or attach a photo.')
        if data.get('image') and not data.get('message'):
            data['message'] = DEFAULT_IMAGE_QUESTION
        return data


class VoiceForm(forms.Form):
    audio = forms.FileField()
    language = forms.ChoiceField(choices=[('bn', 'বাংলা'), ('en', 'English'), ('auto', 'Auto')])
