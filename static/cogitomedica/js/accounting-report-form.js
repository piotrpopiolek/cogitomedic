(function () {
  const form = document.getElementById("accounting-report-form");
  if (!form) {
    return;
  }

  const dateFrom = form.querySelector("#date_from");
  const dateTo = form.querySelector("#date_to");
  const reportMode = form.querySelector("#report_mode");
  const csvLink = form.querySelector("[data-export-csv]");
  const xlsxLink = form.querySelector("[data-export-xlsx]");
  const csvBase = form.dataset.exportCsvUrl || "";
  const xlsxBase = form.dataset.exportXlsxUrl || "";
  const pageSizeInput = form.querySelector('input[name="page_size"]');
  const debounceMs = Number(form.dataset.autoSubmitDebounceMs || 300);

  let timer = null;

  function buildQueryString() {
    const params = new URLSearchParams();
    if (reportMode && reportMode.value) {
      params.set("report_mode", reportMode.value);
    }
    if (dateFrom && dateFrom.value) {
      params.set("date_from", dateFrom.value);
    }
    if (dateTo && dateTo.value) {
      params.set("date_to", dateTo.value);
    }
    if (pageSizeInput && pageSizeInput.value) {
      params.set("page_size", pageSizeInput.value);
    }
    const encoded = params.toString();
    return encoded ? "?" + encoded : "";
  }

  function updateExportLinks() {
    const queryString = buildQueryString();
    if (csvLink && csvBase) {
      csvLink.href = csvBase + queryString;
    }
    if (xlsxLink && xlsxBase) {
      xlsxLink.href = xlsxBase + queryString;
    }
  }

  function submitForm() {
    updateExportLinks();
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit();
    } else {
      form.submit();
    }
  }

  function scheduleAutoSubmit() {
    window.clearTimeout(timer);
    timer = window.setTimeout(submitForm, debounceMs);
  }

  form.addEventListener("change", function (event) {
    const target = event.target;
    if (!target || !target.name) {
      return;
    }
    if (target.name === "report_mode") {
      window.clearTimeout(timer);
      submitForm();
      return;
    }
    if (target.name === "date_from" || target.name === "date_to") {
      scheduleAutoSubmit();
    }
  });

  updateExportLinks();
})();
