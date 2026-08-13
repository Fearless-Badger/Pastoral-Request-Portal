// Character counter for the request textarea. It stays out of the way until the
// text is close to the cap, so someone writing a few sentences never sees a limit
// they were never going to reach.
//
// Both numbers are read off the element itself: maxlength, which Django renders
// from the form field's max_length, and data-counter-at. Nothing is duplicated
// here, so changing REQUEST_MAX_LENGTH or COUNTER_THRESHOLD in forms.py is enough.

(function () {
  var field = document.querySelector("[data-counter-at]");
  var counter = document.querySelector("[data-counter]");
  var status = document.querySelector("[data-counter-status]");

  if (!field || !counter) {
    return;
  }

  var max = Number(field.getAttribute("maxlength"));
  var showAt = Number(field.dataset.counterAt);
  var announce;

  // Without maxlength there is nothing to count down from, and a broken counter
  // reading "-42 characters left" on a live page is worse than none at all.
  if (!max || !showAt) {
    return;
  }

  function update() {
    counter.hidden = field.value.length < showAt;
    if (counter.hidden) {
      return;
    }

    var left = max - field.value.length;
    var noun = left === 1 ? " character left" : " characters left";

    counter.textContent = left.toLocaleString() + noun;
    counter.classList.toggle("counter--full", left === 0);

    // Screen readers get the same text, but only once typing pauses. The visible
    // counter is aria-hidden and this region carries the announcement, because
    // updating a live region on every keystroke would read out all thousand
    // numbers on the way down to the cap.
    if (status) {
      clearTimeout(announce);
      announce = setTimeout(function () {
        status.textContent = counter.textContent;
      }, 1000);
    }
  }

  field.addEventListener("input", update);

  // Also on load. A rejected POST re-renders with the text still in place, and
  // the counter has to already be showing when it does.
  update();
})();
