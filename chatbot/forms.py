from django import forms


class QuestionForm(forms.Form):
    message = forms.CharField(max_length=2000, strip=True, label='Your question',
                              error_messages={'required': 'Type a question first.'})
