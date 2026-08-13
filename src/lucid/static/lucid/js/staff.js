// Opens a request row's dialog. Closing is handled by the markup itself, with
// method="dialog" forms, so the only jobs left here are opening and the
// click-outside dismiss.

document.querySelectorAll("[data-dialog]").forEach(function (trigger) {
  var dialog = document.getElementById(trigger.dataset.dialog);
  if (!dialog) {
    return;
  }

  trigger.addEventListener("click", function () {
    dialog.showModal();
  });

  // Once open, the dialog element fills the viewport and the backdrop is a
  // pseudo-element, so a click that lands on the dialog itself rather than on
  // one of its children means the outside was clicked. This relies on the panel
  // having no padding of its own; the padding lives on the sections inside.
  dialog.addEventListener("click", function (event) {
    if (event.target === dialog) {
      dialog.close();
    }
  });
});
