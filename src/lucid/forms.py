from django import forms

from . import turnstile
from .models import PrayerRequest

# Turnstile checks who is submitting, not how much. This is what stops one POST
# pushing an unbounded blob into the database. Enforced on the form rather than
# the model, which keeps it migration-free.
REQUEST_MAX_LENGTH = 15_000

# The counter stays hidden until the text reaches this, so the ordinary case of a
# few sentences is never shown a limit it was never going to reach.
COUNTER_THRESHOLD = 14_000


class PrayerRequestForm(forms.ModelForm):
    # Declared only to attach max_length, since the model's TextField has none.
    # widget=Textarea is load-bearing, not decorative: forms.CharField defaults to
    # TextInput, which would quietly collapse this into a one-line box. Django
    # renders maxlength onto the textarea from max_length, so the browser's own
    # stop and the server-side check come from a single number, and
    # prayer_form.js reads both numbers off the element rather than repeating them.
    request = forms.CharField(
        max_length=REQUEST_MAX_LENGTH,
        widget=forms.Textarea(attrs={"data-counter-at": COUNTER_THRESHOLD}),
    )

    class Meta:
        model = PrayerRequest
        # name is already max_length=100 on the model, so ModelForm caps it here
        # for free.
        fields: list[str] = ["name", "request"]

    def clean(self):
        cleaned_data = super().clean()

        # The token arrives as "cf-turnstile-response", which is not a valid
        # Python identifier and so cannot be a declared field. self.data is
        # already the POST QueryDict though, so the form reads it directly and the
        # view needs no plumbing at all. is_enabled() comes first so `and`
        # short-circuits and nothing calls out when Turnstile is switched off.
        if turnstile.is_enabled() and not turnstile.verify(
            self.data.get("cf-turnstile-response", "")
        ):
            raise forms.ValidationError(
                "Please complete the verification below and submit again."
            )

        return cleaned_data
