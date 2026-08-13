from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import PrayerRequestForm
from .models import PrayerRequest

PER_PAGE = 25

# Status tabs. "active" is the landing view: everything a pastor might still act
# on, which means archived is out of the way until asked for.
STATUS_FILTERS = {
    "active": [PrayerRequest.Status.NEW, PrayerRequest.Status.PRAYED_FOR],
    "new": [PrayerRequest.Status.NEW],
    "prayed": [PrayerRequest.Status.PRAYED_FOR],
    "archived": [PrayerRequest.Status.ARCHIVED],
    "all": None,
}
DEFAULT_STATUS = "active"

# pk breaks ties. Two requests submitted in the same instant would otherwise
# have an undefined order, which lets Paginator repeat or drop rows across pages.
SORTS = {
    "newest": ("-submitted_at", "-pk"),
    "oldest": ("submitted_at", "pk"),
}
DEFAULT_SORT = "newest"

WINDOWS = {"7": 7, "30": 30}


def submit_request(request):
    if request.method == "POST":
        form = PrayerRequestForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Thank you. Our church family will be praying for you.")
            return redirect("submit_request")
    else:
        form = PrayerRequestForm()

    return render(
        request,
        "lucid/prayer_form.html",
        {
            "form": form,
            # Only so the template can draw the widget. Verification itself lives
            # in the form's clean(), which is why nothing else in this view moved.
            "turnstile_site_key": settings.TURNSTILE_SITE_KEY,
        },
    )


@staff_member_required
def staff_requests(request):
    if request.method == "POST":
        return _change_status(request)

    # Every param falls back to its default rather than erroring, so a mangled
    # or hand-edited URL still renders something useful.
    status = request.GET.get("status", DEFAULT_STATUS)
    if status not in STATUS_FILTERS:
        status = DEFAULT_STATUS

    sort = request.GET.get("sort", DEFAULT_SORT)
    if sort not in SORTS:
        sort = DEFAULT_SORT

    days = request.GET.get("days", "")
    query = request.GET.get("q", "").strip()

    requests = PrayerRequest.objects.all()

    if STATUS_FILTERS[status] is not None:
        requests = requests.filter(status__in=STATUS_FILTERS[status])

    if days in WINDOWS:
        requests = requests.filter(
            submitted_at__gte=timezone.now() - timedelta(days=WINDOWS[days])
        )
    else:
        days = ""

    if query:
        requests = requests.filter(Q(name__icontains=query) | Q(request__icontains=query))

    page = Paginator(requests.order_by(*SORTS[sort]), PER_PAGE).get_page(
        request.GET.get("page")
    )

    return render(
        request,
        "lucid/staff_requests.html",
        {
            "page": page,
            "status": status,
            "sort": sort,
            "days": days,
            "query": query,
            "tabs": _tabs(status),
            # Feeds the status dropdown in each row's modal.
            "statuses": PrayerRequest.Status.choices,
        },
    )


def _tabs(current):
    """Status tabs with their counts, so a pastor can see the backlog at a glance."""
    counts = dict(
        PrayerRequest.objects.values_list("status").annotate(n=Count("status"))
    )
    labels = {
        "active": "Needs attention",
        "new": "New",
        "prayed": "Prayed for",
        "archived": "Archived",
        "all": "All",
    }

    tabs = []
    for key, statuses in STATUS_FILTERS.items():
        included = counts.keys() if statuses is None else statuses
        tabs.append(
            {
                "key": key,
                "label": labels[key],
                "count": sum(counts.get(s, 0) for s in included),
                "current": key == current,
            }
        )
    return tabs


def _change_status(request):
    status = request.POST.get("status", "")

    # Never trust the posted value. Without this a crafted POST could write an
    # arbitrary string into a column that is supposed to hold only three.
    if status not in PrayerRequest.Status.values:
        return HttpResponseBadRequest("Unknown status.")

    prayer_request = get_object_or_404(PrayerRequest, pk=request.POST.get("pk"))
    prayer_request.status = status
    # updated_at has to be named explicitly. With update_fields, auto_now still
    # sets the attribute but only listed columns are written.
    prayer_request.save(update_fields=["status", "updated_at"])

    messages.success(
        request,
        f"Marked as {PrayerRequest.Status(status).label.lower()}.",
    )

    # The form posts to the current URL including its querystring, so this lands
    # back on the same filtered page rather than resetting to the default view.
    return redirect(request.get_full_path())
