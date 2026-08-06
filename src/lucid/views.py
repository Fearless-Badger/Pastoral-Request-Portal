from django.contrib import messages
from django.shortcuts import redirect, render

from .forms import PrayerRequestForm


def submit_request(request):
    if request.method == "POST":
        form = PrayerRequestForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Thank you. Your request has been sent to our pastors.")
            return redirect("submit_request")
    else:
        form = PrayerRequestForm()

    return render(request, "lucid/prayer_form.html", {"form": form})
