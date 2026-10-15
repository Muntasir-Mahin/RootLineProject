from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import GroupAdmin
from django.contrib.auth.models import Group


class RoleGroupForm(forms.ModelForm):
    members = forms.ModelMultipleChoiceField(
        queryset=get_user_model().objects.all(), required=False,
        widget=FilteredSelectMultiple('members', is_stacked=False),
        help_text='Dashboard access also requires Active and Staff status on each user.',
    )

    class Meta:
        model = Group
        fields = ('name', 'permissions', 'members')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['members'].initial = self.instance.user_set.all()

    def _save_m2m(self):
        super()._save_m2m()
        self.instance.user_set.set(self.cleaned_data['members'])


class RoleGroupAdmin(GroupAdmin):
    form = RoleGroupForm
