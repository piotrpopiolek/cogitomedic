/**
 * Doctor Befund form: intake summary, lesion groups, buildPayload, draft, publish.
 * Expects #doctor-panel-data (json_script) with { documentId, apiBase, context, ui }.
 */
(function () {
  "use strict";

  const dataEl = document.getElementById("doctor-panel-data");
  let PANEL = {};
  if (dataEl && dataEl.textContent) {
    try {
      PANEL = JSON.parse(dataEl.textContent);
    } catch (e) {
      PANEL = {};
    }
  }
  const DOC_ID =
    PANEL.documentId ||
    ((window.location.pathname.match(/[0-9a-fA-F-]{36}/) || [])[0] || "");
  const API = PANEL.apiBase || "/api/v1";
  const CTX = PANEL.context || {};
  /** Doctor UI strings from ``PANEL.ui`` (``get_doctor_ui`` / TranslationValue); no hardcoded fallbacks. */
  function uiText(key) {
    const v = PANEL.ui && PANEL.ui[key];
    return v == null || v === "" ? "" : String(v);
  }
  function formatUiPlaceholders(template, values) {
    if (!template) return "";
    const m = values || {};
    return String(template).replace(/\{(\w+)\}/g, function (_, name) {
      return Object.prototype.hasOwnProperty.call(m, name)
        ? String(m[name])
        : "{" + name + "}";
    });
  }
  function lesionGroupTitleLine(zeroBasedIndex) {
    return (
      uiText("lesion_group_prefix") +
      " " +
      (zeroBasedIndex + 1) +
      " – " +
      uiText("lesion_header")
    );
  }
  function unnamedPresetLabel(zeroBasedIndex) {
    return formatUiPlaceholders(uiText("favorite_preset_unnamed"), {
      n: zeroBasedIndex + 1,
    });
  }
  const UI = Object.freeze({
    bodyMapTitle: uiText("body_map_title"),
    bodyMapHint: uiText("body_map_hint"),
    bodyMapNoMarkers: uiText("body_map_no_markers"),
    bodyMapToggleHint: uiText("body_map_toggle_hint"),
    templateSelectPlaceholder: uiText("template_select_placeholder"),
    msgFavoriteApplied: uiText("msg_favorite_applied"),
    msgError: uiText("msg_error"),
    msgNetwork: uiText("msg_network_error"),
    msgSaveSuccess: uiText("msg_save_success"),
    msgPublishSuccess: uiText("msg_publish_success"),
    msgRetrySuccess: uiText("msg_retry_success"),
    msgSessionExpired: uiText("msg_session_expired"),
    msgTemplateLoadError: uiText("msg_template_load_error"),
    msgLesionRequired: uiText("msg_lesion_required"),
    lesionHeader: uiText("lesion_header"),
    patientLabel: uiText("patient_label"),
    intakeAnamnesisHeading: uiText("intake_summary_anamnesis_heading"),
    intakeReceptionNoteHeading: uiText("intake_summary_reception_note_heading"),
    templateNameFallback: uiText("template_name_fallback"),
    externalPdfRejectBtn: uiText("external_pdf_reject_btn"),
    externalPdfStatusMatched: uiText("external_pdf_status_matched"),
    externalPdfStatusRejected: uiText("external_pdf_status_rejected"),
    externalPdfStatusMergeFailed: uiText("external_pdf_status_merge_failed"),
    externalPdfStatusAccepted: uiText("external_pdf_status_accepted"),
    externalPdfStatusPendingUpload: uiText("external_pdf_status_pending_upload"),
    externalPdfStatusUploadFailed: uiText("external_pdf_status_upload_failed"),
    externalPdfPreviewHint: uiText("external_pdf_preview_hint"),
    externalPdfPreviewMergeWarning: uiText("external_pdf_preview_merge_warning"),
    msgPublishPreviewRequired: uiText("msg_publish_preview_required"),
    bannerPublishedTitle: uiText("banner_published_title"),
    bannerPublishedBody: uiText("banner_published_body"),
    bannerRevokedTitle: uiText("banner_revoked_title"),
    bannerRevokedBody: uiText("banner_revoked_body"),
    bannerRevisionTitle: uiText("banner_revision_title"),
    bannerRevisionBody: uiText("banner_revision_body"),
    btnSaveDraft: uiText("btn_save_draft"),
    btnPreviewPdf: uiText("btn_preview_pdf"),
    btnPreviewPublished: uiText("btn_preview_published"),
    btnPreviewRevision: uiText("btn_preview_revision"),
    btnPublish: uiText("btn_publish"),
    btnRepublish: uiText("btn_republish"),
    btnStartRevision: uiText("btn_start_revision"),
    btnDiscardRevision: uiText("btn_discard_revision"),
    modalStartRevisionTitle: uiText("modal_start_revision_title"),
    modalStartRevisionBody: uiText("modal_start_revision_body"),
    modalStartRevisionConfirm: uiText("modal_start_revision_confirm"),
    modalStartRevisionCancel: uiText("modal_start_revision_cancel"),
    modalDiscardRevisionTitle: uiText("modal_discard_revision_title"),
    modalDiscardRevisionBody: uiText("modal_discard_revision_body"),
    modalDiscardRevisionConfirm: uiText("modal_discard_revision_confirm"),
    modalRevokePublicationTitle: uiText("modal_revoke_publication_title"),
    modalRevokePublicationBody: uiText("modal_revoke_publication_body"),
    modalRevokePublicationConfirm: uiText("modal_revoke_publication_confirm"),
    modalRevokePublicationCancel: uiText("modal_revoke_publication_cancel"),
    msgRevokePublicationSuccess: uiText("msg_revoke_publication_success"),
    msgRevisionStarted: uiText("msg_revision_started"),
    msgRevisionDiscarded: uiText("msg_revision_discarded"),
    msgAmendIntentRequired: uiText("msg_amend_intent_required"),
    msgNoPendingRevision: uiText("msg_no_pending_revision"),
    intakeSectionPaperTitle: uiText("detail_intake_section_paper_title"),
    paperIntakeNotice: uiText("detail_paper_intake_notice"),
    paperAuthHeading: uiText("detail_paper_auth_heading"),
    paperAuthByLabel: uiText("detail_paper_auth_by_label"),
    paperAuthAtLabel: uiText("detail_paper_auth_at_label"),
    paperAuthReasonLabel: uiText("detail_paper_auth_reason_label"),
  });

  function el(id) {
    return document.getElementById(id);
  }
  function escapeHtml(s) {
    if (s == null || s === undefined) return "";
    const t = String(s);
    return t
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }
  function patientDobDisplay(value) {
    if (value == null || value === "") return "—";
    const t = String(value).trim();
    if (!t || t === "None" || t === "null") return "—";
    return escapeHtml(t);
  }
  function formatPaperAuthAtIso(iso) {
    if (!iso || typeof iso !== "string") return "—";
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return escapeHtml(iso);
      return escapeHtml(d.toLocaleString());
    } catch (e) {
      return escapeHtml(iso);
    }
  }
  /** Read-only body map (same normalized coords as tablet: x,y in [0,1] on combined front|back image). */
  function renderReadonlyBodyMapHtml(points, imgUrl) {
    if (!imgUrl) return "";
    var pts = Array.isArray(points) ? points : [];
    var markers = "";
    pts.forEach(function (p, i) {
      var x = typeof p.x === "number" ? p.x : parseFloat(p.x);
      var y = typeof p.y === "number" ? p.y : parseFloat(p.y);
      if (isNaN(x) || isNaN(y)) return;
      var left = x * 100;
      var top = y * 100;
      var side = p.side ? String(p.side) : "";
      var label = (side ? side + " " : "") + "#" + (i + 1);
      markers +=
        '<span class="doctor-body-map-marker" style="left:' +
        left +
        "%;top:" +
        top +
        '%" title="' +
        escapeHtml(label) +
        '" role="img" aria-label="' +
        escapeHtml(label) +
        '"></span>';
    });
    var emptyNote = markers
      ? ""
      : '<p class="text-sm text-base-500 dark:text-base-400 mb-2">' +
        escapeHtml(UI.bodyMapNoMarkers) +
        "</p>";
    return (
      '<details class="doctor-body-map-details mt-3 pt-3 border-t border-base-200 dark:border-base-700" open>' +
      '<summary class="doctor-body-map-summary">' +
      '<span class="doctor-body-map-chevron" aria-hidden="true">▶</span>' +
      '<span class="doctor-body-map-summary-text">' +
      '<span class="doctor-body-map-summary-title">' +
      escapeHtml(UI.bodyMapTitle) +
      "</span>" +
      '<span class="doctor-body-map-summary-hint">(' +
      escapeHtml(UI.bodyMapToggleHint) +
      ")</span>" +
      "</span>" +
      "</summary>" +
      '<div class="doctor-body-map-details-inner">' +
      '<p class="text-sm text-base-500 dark:text-base-400 mb-2">' +
      escapeHtml(UI.bodyMapHint) +
      "</p>" +
      emptyNote +
      '<div class="doctor-body-map-outer max-w-2xl">' +
      '<div class="doctor-body-map-wrap relative w-full rounded border border-base-200 dark:border-base-600 overflow-hidden bg-base-50 dark:bg-base-950">' +
      '<img src="' +
      escapeHtml(imgUrl) +
      '" alt="" class="w-full h-auto block" loading="lazy" decoding="async" />' +
      '<div class="doctor-body-map-markers absolute left-0 top-0 w-full h-full pointer-events-none"' +
      (markers ? ' aria-hidden="true"' : "") +
      ">" +
      markers +
      "</div></div></div></div></details>"
    );
  }
  function alertMsg(level, text) {
    const wrap = el("alert-placeholder");
    if (!wrap) return;
    var skin =
      level === "success"
        ? "bg-emerald-50 border-emerald-200 text-emerald-900 dark:bg-emerald-950/50 dark:border-emerald-800 dark:text-emerald-100"
        : level === "warning"
          ? "bg-amber-50 border-amber-200 text-amber-950 dark:bg-amber-950/40 dark:border-amber-800 dark:text-amber-100"
          : "bg-red-50 border-red-200 text-red-900 dark:bg-red-950/50 dark:border-red-800 dark:text-red-100";
    wrap.innerHTML =
      '<div role="alert" class="' +
      skin +
      ' rounded-default border px-4 py-3 text-sm leading-snug shadow-xs">' +
      escapeHtml(text) +
      "</div>";
    try {
      wrap.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (eScroll) {}
  }
  function getCookie(name) {
    const v = document.cookie.match("(^|;) ?" + name + "=([^;]*)(;|$)");
    return v ? v[2] : null;
  }
  function getCsrfToken() {
    const tokenEl = document.querySelector("[name=csrfmiddlewaretoken]");
    return tokenEl ? tokenEl.value : (getCookie("csrftoken") || "").trim();
  }
  function buildDoctorLoginUrl() {
    return "/doctor/login/?next=" + encodeURIComponent(window.location.pathname + window.location.search);
  }
  var authExpiredHandled = false;
  function handleAuthExpired(message) {
    if (authExpiredHandled) return;
    authExpiredHandled = true;
    alertMsg("warning", message || UI.msgSessionExpired || "Session expired.");
    if (typeof releaseEditLockBestEffort === "function") {
      releaseEditLockBestEffort();
    }
    window.setTimeout(function () {
      window.location.href = buildDoctorLoginUrl();
    }, 300);
  }
  function isAuthExpiredResponse(res) {
    return !!(res && res.authExpired);
  }
  function apiFetch(url, opts) {
    opts = opts || {};
    opts.credentials = "same-origin";
    opts.headers = opts.headers || {};
    if (
      opts.body &&
      typeof opts.body === "string" &&
      !opts.headers["Content-Type"]
    )
      opts.headers["Content-Type"] = "application/json";
    opts.headers["Accept"] = "application/json";
    const method = (opts.method || "GET").toUpperCase();
    if (["POST", "PUT", "PATCH", "DELETE"].indexOf(method) !== -1)
      opts.headers["X-CSRFToken"] = getCsrfToken();
    function parseResponseBody(response) {
      const contentType = (response.headers.get("content-type") || "").toLowerCase();
      if (contentType.indexOf("application/json") !== -1) {
        return response.json().catch(function () {
          return {};
        });
      }
      return response.text().then(function (text) {
        if (!text) return {};
        return { raw_response: text.slice(0, 300) };
      }).catch(function () {
        return {};
      });
    }
    return fetch(url, opts).then(function (r) {
      return parseResponseBody(r).then(function (j) {
        if (r.status === 401) {
          handleAuthExpired((j && j.error) || UI.msgSessionExpired);
          return { ok: false, status: r.status, json: j, authExpired: true };
        }
        return { ok: r.ok, status: r.status, json: j };
      });
    });
  }

  function docUrl(pathSuffix) {
    return API + "/medical-documents/" + DOC_ID + pathSuffix;
  }

  var docStatusEarly = (CTX && CTX.status) || "";
  var publishedVersionNoEarly =
    CTX && typeof CTX.published_version_no !== "undefined"
      ? CTX.published_version_no
      : null;
  var hasPendingRevisionEarly = !!(CTX && CTX.has_pending_revision);
  var previewSeenSinceLastSave = docStatusEarly !== "DRAFT";

  function hasPublishedHistory() {
    return docStatus === "PUBLISHED" || publishedVersionNo != null;
  }

  function isDraftAuthoring() {
    return docStatus === "DRAFT" || hasPendingRevision;
  }

  function isPublicationRevoked() {
    var cv = CTX && CTX.current_version;
    return !!(cv && cv.revoked_at);
  }

  function revokeDeliveryComplete() {
    var cv = CTX && CTX.current_version;
    if (!cv) return false;
    return !!(cv.hidrive_sent && cv.sms_sent);
  }

  function isPublishedReadOnly() {
    return (
      docStatus === "PUBLISHED" &&
      !hasPendingRevision &&
      !isPublicationRevoked()
    );
  }

  function setPublishEnabledFromPreviewFlag() {
    var pub = el("btn-publish");
    if (!pub) return;
    if (hasPublishedHistory() && !hasPendingRevision) {
      pub.disabled = true;
      return;
    }
    pub.disabled = !previewSeenSinceLastSave;
  }

  var lastExternalPdfObjUrl = null;
  function revokeLastExternalPdfObjectUrl() {
    if (!lastExternalPdfObjUrl) return;
    try {
      URL.revokeObjectURL(lastExternalPdfObjUrl);
    } catch (eRev) {}
    lastExternalPdfObjUrl = null;
  }

  function openExternalPdfAttachmentInIframe(item) {
    var iframe = el("external-pdf-iframe");
    if (!iframe || !item || !item.id) return;
    revokeLastExternalPdfObjectUrl();
    iframe.src = "about:blank";
    fetch(docUrl("/external-pdfs/" + item.id + "/content"), {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/pdf" },
    })
      .then(function (r) {
        var ct = (r.headers.get("content-type") || "").toLowerCase();
        if (r.status === 401) {
          handleAuthExpired(UI.msgSessionExpired);
          return;
        }
        if (!r.ok) {
          if (ct.indexOf("application/json") !== -1) {
            return r.json().then(function (j) {
              alertMsg("danger", (j && j.error) || UI.msgError + " " + r.status);
            });
          }
          alertMsg("danger", UI.msgError + " " + r.status);
          return;
        }
        return r.blob().then(function (blob) {
          var url = URL.createObjectURL(blob);
          lastExternalPdfObjUrl = url;
          iframe.src = url;
        });
      })
      .catch(function () {
        alertMsg("danger", UI.msgNetwork);
      });
  }

  function externalPdfStatusLabel(status) {
    if (status === "REJECTED") return UI.externalPdfStatusRejected;
    if (status === "MERGE_FAILED") return UI.externalPdfStatusMergeFailed;
    if (status === "ACCEPTED") return UI.externalPdfStatusAccepted;
    if (status === "PENDING_UPLOAD") return UI.externalPdfStatusPendingUpload;
    if (status === "UPLOAD_FAILED") return UI.externalPdfStatusUploadFailed;
    return UI.externalPdfStatusMatched;
  }

  /** First previewable attachment: prefer MATCHED, then MERGE_FAILED / ACCEPTED; skip REJECTED-only lists. */
  function pickDefaultExternalPdfItem(items) {
    if (!items || !items.length) return null;
    var i;
    for (i = 0; i < items.length; i++) {
      if (items[i].status === "MATCHED") return items[i];
    }
    for (i = 0; i < items.length; i++) {
      var s = items[i].status;
      if (s === "MERGE_FAILED" || s === "ACCEPTED") return items[i];
    }
    return null;
  }

  function loadExternalPdfs() {
    var panel = el("external-pdfs-panel");
    var listEl = el("external-pdfs-list");
    var hintEl = el("external-pdfs-empty");
    if (!panel || !listEl) return;
    apiFetch(docUrl("/external-pdfs"), { method: "GET" }).then(function (res) {
      if (isAuthExpiredResponse(res)) return;
      if (!res.ok) return;
      var items = (res.json && res.json.items) || [];
      listEl.innerHTML = "";
      if (hintEl) {
        hintEl.textContent = UI.externalPdfPreviewHint;
        hintEl.classList.toggle("hidden", items.length > 0);
      }
      panel.classList.toggle("hidden", items.length === 0);
      items.forEach(function (item) {
        var li = document.createElement("li");
        li.className = "flex flex-wrap items-center gap-2 justify-between border border-base-200 dark:border-base-700 rounded-default px-3 py-2";
        var left = document.createElement("div");
        left.className = "flex flex-col gap-1 min-w-0";
        var nameBtn = document.createElement("button");
        nameBtn.type = "button";
        nameBtn.className =
          "text-left text-primary-600 hover:underline dark:text-primary-400 truncate font-medium bg-transparent border-0 p-0 cursor-pointer";
        nameBtn.textContent = item.filename || item.id;
        nameBtn.addEventListener("click", function () {
          openExternalPdfAttachmentInIframe(item);
        });
        var st = document.createElement("span");
        st.className = "text-xs text-base-500 dark:text-base-400";
        st.textContent = externalPdfStatusLabel(item.status);
        left.appendChild(nameBtn);
        left.appendChild(st);
        li.appendChild(left);
        if (item.status === "MATCHED" && !PANEL.externalUploadReadOnly) {
          var rej = document.createElement("button");
          rej.type = "button";
          rej.className =
            "inline-flex items-center rounded-default border border-red-200 px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50 dark:border-red-800 dark:text-red-300 shrink-0";
          rej.textContent = UI.externalPdfRejectBtn;
          rej.addEventListener("click", function () {
            apiFetch(docUrl("/external-pdfs/" + item.id + "/reject"), {
              method: "POST",
              body: "{}",
            }).then(function (r2) {
              if (isAuthExpiredResponse(r2)) return;
              if (!r2.ok) {
                alertMsg(
                  "danger",
                  responseErrorMessage(r2, UI.msgError + " " + r2.status)
                );
                return;
              }
              alertMsg("success", UI.msgSaveSuccess);
              loadExternalPdfs();
            });
          });
          li.appendChild(rej);
        }
        listEl.appendChild(li);
      });
      var autoItem = pickDefaultExternalPdfItem(items);
      if (autoItem) openExternalPdfAttachmentInIframe(autoItem);
    });
  }

  function responseErrorMessage(res, fallback) {
    if (isAuthExpiredResponse(res)) return "";
    if (!res || !res.json) return fallback;
    return res.json.error || res.json.detail || res.json.raw_response || fallback;
  }

  if (!DOC_ID) {
    console.warn("Doctor panel init aborted: missing medical document id.");
    return;
  }

  var docStatus = docStatusEarly;
  var publishedVersionNo = publishedVersionNoEarly;
  var hasPendingRevision = hasPendingRevisionEarly;

  /**
   * Edit lock release:
   * - Intentional leave (list / logout / publish / auth): unlock immediately (no timer).
   * - Real unload (Back, close tab, hard navigation): unlock on pagehide when NOT bfcache.
   * - Tab switch / mobile freeze into bfcache (pagehide.persisted): keep the lock (P0).
   */
  var befundFormDirty = false;

  function releaseEditLockBestEffort() {
    if (!isDraftAuthoring()) return;
    var token = getCsrfToken();
    if (!token) return;
    var url = docUrl("/unlock");
    try {
      fetch(url, {
        method: "POST",
        credentials: "same-origin",
        keepalive: true,
        headers: {
          "X-CSRFToken": token,
          "Content-Type": "application/json",
        },
        body: "{}",
      }).catch(function () {});
    } catch (e) {}
  }

  function releaseEditLockOnIntentionalLeave() {
    // If the form is dirty, browser beforeunload may still cancel navigation —
    // defer unlock to pagehide (!persisted) so cancel keeps the semaphore.
    if (befundFormDirty) return;
    releaseEditLockBestEffort();
  }

  function isLeavingDocumentEditAnchor(anchor) {
    if (!anchor || anchor.target === "_blank") return false;
    if (anchor.hasAttribute("download")) return false;
    var href = anchor.getAttribute("href");
    if (!href || href.charAt(0) === "#") return false;
    var url;
    try {
      url = new URL(href, window.location.href);
    } catch (e) {
      return false;
    }
    if (url.origin !== window.location.origin) return true;
    var cur = (window.location.pathname || "").replace(/\/$/, "");
    var next = (url.pathname || "").replace(/\/$/, "");
    return next !== cur;
  }

  document.addEventListener(
    "click",
    function (ev) {
      var a =
        ev.target &&
        ev.target.closest &&
        ev.target.closest("a[href]");
      if (!a || !isDraftAuthoring()) return;
      if (
        a.classList.contains("js-release-document-lock") ||
        isLeavingDocumentEditAnchor(a)
      ) {
        releaseEditLockOnIntentionalLeave();
      }
    },
    true
  );

  document.addEventListener(
    "submit",
    function (ev) {
      var form = ev.target;
      if (!form || !isDraftAuthoring()) return;
      var action = (form.getAttribute("action") || "").toLowerCase();
      if (
        form.classList.contains("js-release-document-lock") ||
        action.indexOf("logout") !== -1
      ) {
        // Logout POST can be slow — unlock immediately (do not wait for pagehide).
        releaseEditLockBestEffort();
        befundFormDirty = false;
      }
    },
    true
  );

  window.addEventListener("pagehide", function (e) {
    // bfcache / freeze: keep lock. Back, close, navigate away: release.
    if (e && e.persisted) return;
    releaseEditLockBestEffort();
  });

  var befundFormEl = el("befund-form");
  if (befundFormEl) {
    befundFormEl.addEventListener("input", function () {
      befundFormDirty = true;
    });
    befundFormEl.addEventListener("change", function () {
      befundFormDirty = true;
    });
  }
  window.addEventListener("beforeunload", function (e) {
    if (!isDraftAuthoring() || !befundFormDirty) return;
    // Warning only — unlock happens on pagehide when navigation is not cancelled.
    e.preventDefault();
    e.returnValue = "";
  });

  function renderPaperIntakeMeta() {
    const metaEl = el("paper-intake-meta");
    const titleEl = el("doctor-intake-section-title");
    if (CTX.source_type !== "PAPER_INTAKE") {
      if (metaEl) {
        metaEl.innerHTML = "";
        metaEl.classList.add("hidden");
        metaEl.setAttribute("hidden", "hidden");
      }
      return;
    }
    if (titleEl && UI.intakeSectionPaperTitle) {
      titleEl.textContent = UI.intakeSectionPaperTitle;
    }
    if (!metaEl) return;
    const parts = [];
    if (UI.paperIntakeNotice) {
      parts.push(
        '<div class="rounded-default border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950 dark:border-amber-800/80 dark:bg-amber-950/40 dark:text-amber-100">' +
          escapeHtml(UI.paperIntakeNotice) +
          "</div>"
      );
    }
    const auth = CTX.paper_intake_authorization;
    if (
      auth &&
      (auth.authorized_by_username || auth.authorized_at || auth.reason)
    ) {
      let rows = "";
      if (auth.authorized_by_username) {
        rows +=
          '<div class="grid grid-cols-1 gap-1 sm:grid-cols-[minmax(0,10rem)_1fr] sm:gap-x-3"><dt class="font-medium text-base-600 dark:text-base-400">' +
          escapeHtml(UI.paperAuthByLabel) +
          '</dt><dd class="text-base-900 dark:text-base-100">' +
          escapeHtml(auth.authorized_by_username) +
          "</dd></div>";
      }
      if (auth.authorized_at) {
        rows +=
          '<div class="grid grid-cols-1 gap-1 sm:grid-cols-[minmax(0,10rem)_1fr] sm:gap-x-3"><dt class="font-medium text-base-600 dark:text-base-400">' +
          escapeHtml(UI.paperAuthAtLabel) +
          '</dt><dd class="text-base-900 dark:text-base-100">' +
          formatPaperAuthAtIso(auth.authorized_at) +
          "</dd></div>";
      }
      if (auth.reason) {
        rows +=
          '<div class="grid grid-cols-1 gap-1 sm:grid-cols-[minmax(0,10rem)_1fr] sm:gap-x-3"><dt class="font-medium text-base-600 dark:text-base-400">' +
          escapeHtml(UI.paperAuthReasonLabel) +
          '</dt><dd class="text-base-900 dark:text-base-100 whitespace-pre-wrap">' +
          escapeHtml(auth.reason) +
          "</dd></div>";
      }
      parts.push(
        '<div class="rounded-default border border-base-200 bg-white px-4 py-3 text-sm dark:border-base-700 dark:bg-base-900">' +
          '<div class="mb-2 font-medium text-base-900 dark:text-base-100">' +
          escapeHtml(UI.paperAuthHeading) +
          "</div>" +
          '<div class="space-y-2">' +
          rows +
          "</div></div>"
      );
    }
    metaEl.innerHTML = parts.join("");
    metaEl.classList.remove("hidden");
    metaEl.removeAttribute("hidden");
  }

  renderPaperIntakeMeta();

  // Intake summary: patient + anamnesis – escape all values to prevent XSS
  if (CTX && CTX.intake_summary) {
    const p = CTX.intake_summary.patient;
    if (p) {
      const nameEl = el("patient-name");
      if (nameEl) nameEl.textContent = (p.last_name || "") + ", " + (p.first_name || "");
      let html =
        "<p><strong>" +
        escapeHtml(UI.patientLabel) +
        "</strong> " +
        escapeHtml(p.last_name) +
        ", " +
        escapeHtml(p.first_name) +
        " · " +
        patientDobDisplay(p.date_of_birth) +
        "</p>";
      const questions = CTX.intake_summary.anamnesis_questions || [];
      if (questions.length) {
        html +=
          '<p class="mb-2 mt-2"><strong>' +
          escapeHtml(UI.intakeAnamnesisHeading) +
          "</strong></p>";
        questions.forEach(function (q) {
          const answer = q.answer || {};
          const selected = answer.selected_option_codes || [];
          const optionsByCode = {};
          (q.options || []).forEach(function (opt) {
            optionsByCode[opt.option_code] = opt.label || opt.option_code;
          });
          const labels = selected.map(function (code) {
            return optionsByCode[code] || code;
          });
          let answerText = labels.join(", ");
          if (answer.free_text)
            answerText =
              (answerText ? answerText + " — " : "") + answer.free_text;
          html +=
            '<p class="small mb-1"><strong>' +
            escapeHtml(q.question_text || q.question_code) +
            '</strong><br/><span class="text-muted">' +
            escapeHtml(answerText || "—") +
            "</span></p>";
        });
      }
      const summaryEl = el("intake-summary");
      if (summaryEl) summaryEl.innerHTML = html;
      const bodyMapPts = CTX.intake_summary.body_map_data;
      const bodyMapUrl = PANEL.bodyMapImageUrl || "";
      if (summaryEl && CTX.source_type !== "PAPER_INTAKE") {
        summaryEl.insertAdjacentHTML(
          "beforeend",
          renderReadonlyBodyMapHtml(bodyMapPts, bodyMapUrl)
        );
      }
      var receptionNote = String(
        (CTX.intake_summary && CTX.intake_summary.reception_note) || ""
      ).trim();
      var noteSlot = el("intake-reception-note");
      var noteTextEl = el("intake-reception-note-text");
      if (!receptionNote && noteTextEl) {
        receptionNote = String(noteTextEl.textContent || "").trim();
      }
      if (receptionNote && !noteSlot) {
        var banner = document.createElement("section");
        banner.id = "intake-reception-note";
        banner.className =
          "mb-4 rounded-default border border-amber-400 bg-amber-50 px-4 py-3 text-sm dark:border-amber-600 dark:bg-amber-950/50";
        banner.setAttribute("role", "note");
        banner.innerHTML =
          '<div class="mb-1 font-semibold text-amber-950 dark:text-amber-100">' +
          escapeHtml(UI.intakeReceptionNoteHeading) +
          "</div>" +
          '<p id="intake-reception-note-text" class="mb-0 whitespace-pre-wrap text-base-900 dark:text-base-100">' +
          escapeHtml(receptionNote) +
          "</p>";
        var intakeSection = el("doctor-intake-section-title");
        if (intakeSection && intakeSection.parentNode) {
          intakeSection.parentNode.parentNode.insertBefore(
            banner,
            intakeSection.parentNode
          );
        }
      }
      const bodyMapUrl = PANEL.bodyMapImageUrl || "";
      if (summaryEl && CTX.source_type !== "PAPER_INTAKE") {
        summaryEl.insertAdjacentHTML(
          "beforeend",
          renderReadonlyBodyMapHtml(bodyMapPts, bodyMapUrl)
        );
      }
    }
  }

  const authoringLocale =
    CTX && CTX.authoring_locale ? CTX.authoring_locale : "de-DE";

  var skipBefundFormUi = !!PANEL.externalUploadReadOnly;
  if (
    PANEL.externalUploadReadOnly &&
    PANEL.externalUploadLoadAttachmentPanel !== false
  ) {
    loadExternalPdfs();
  }

  /** Shared with ``buildPayload`` (IIFE scope); set when Befund form UI is active. */
  let selectedTemplate = null;

  if (!skipBefundFormUi) {
  const container = el("lesion-groups-container");
  const tpl = document.getElementById("lesion-group-tpl");
  const hasLesionUi = !!(container && tpl);
  const templateSelectEl = el("doctor-template-select");
  const summaryFavoriteSelectEl = el("summary-favorite-select");
  const applySummaryFavoriteBtn = el("btn-apply-summary-favorite");
  let doctorTemplates = [];

  function setSelectOptions(selectEl, options, placeholder) {
    if (!selectEl) return;
    selectEl.innerHTML = "";
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = placeholder || "—";
    selectEl.appendChild(empty);
    options.forEach(function (opt) {
      const optionEl = document.createElement("option");
      optionEl.value = String(opt.value);
      optionEl.textContent = opt.label;
      selectEl.appendChild(optionEl);
    });
  }

  function findTemplateById(templateId) {
    if (!templateId) return null;
    for (let i = 0; i < doctorTemplates.length; i++) {
      if (String(doctorTemplates[i].id) === String(templateId)) return doctorTemplates[i];
    }
    return null;
  }

  function lesionFavorites() {
    if (!selectedTemplate || !Array.isArray(selectedTemplate.lesion_group_favorites)) return [];
    return selectedTemplate.lesion_group_favorites;
  }

  function summaryFavorites() {
    if (!selectedTemplate) return [];
    if (selectedTemplate.template_body) {
      return [
        {
          name: selectedTemplate.name || UI.templateNameFallback,
          text: selectedTemplate.template_body,
        },
      ];
    }
    return [];
  }

  function refreshFavoriteSelects() {
    const placeholder = UI.templateSelectPlaceholder;
    const lesionOptions = lesionFavorites().map(function (fav, idx) {
      return { value: idx, label: fav.name || unnamedPresetLabel(idx) };
    });
    const summaryOptions = summaryFavorites().map(function (fav, idx) {
      return { value: idx, label: fav.name || unnamedPresetLabel(idx) };
    });
    if (container) {
      container.querySelectorAll(".lesion-favorite-select").forEach(function (selectEl) {
        setSelectOptions(selectEl, lesionOptions, placeholder);
      });
    }
    setSelectOptions(summaryFavoriteSelectEl, summaryOptions, placeholder);
  }

  function applyLesionFavorite(section, favorite) {
    if (!section || !favorite) return;
    section.querySelectorAll(".lesion-feature").forEach(function (cb) {
      cb.checked = false;
    });
    (favorite.dermatoscopic_features || []).forEach(function (feature) {
      const cb = section.querySelector('.lesion-feature[value="' + feature + '"]');
      if (cb) cb.checked = true;
    });
    section.querySelectorAll(".lesion-clinical").forEach(function (rb) {
      rb.checked = false;
    });
    const clinical = section.querySelector(
      '.lesion-clinical[value="' + (favorite.clinical_assessment || "UNREMARKABLE") + '"]'
    );
    if (clinical) clinical.checked = true;
    section.querySelectorAll(".lesion-malignancy").forEach(function (rb) {
      rb.checked = false;
    });
    const malignancy = section.querySelector(
      '.lesion-malignancy[value="' + (favorite.malignancy_risk || "NO_SUSPICION") + '"]'
    );
    if (malignancy) malignancy.checked = true;
    const textEl = section.querySelector(".lesion-text");
    if (textEl) textEl.value = favorite.text || "";
  }

  let lesionGroupIndex = 0;
  function addLesionGroup(initialData) {
    if (!hasLesionUi) return;
    const frag = tpl.content.cloneNode(true);
    const section = frag.querySelector(".lesion-group");
    section.setAttribute("data-group-index", String(lesionGroupIndex));
    const titleEl = section.querySelector(".lesion-group-title");
    if (titleEl) titleEl.textContent = lesionGroupTitleLine(lesionGroupIndex);
    const clinicalRadios = section.querySelectorAll(".lesion-clinical");
    const malignancyRadios = section.querySelectorAll(".lesion-malignancy");
    clinicalRadios.forEach(function (r) {
      r.name = "lesion_grp_" + lesionGroupIndex + "_clinical";
    });
    malignancyRadios.forEach(function (r) {
      r.name = "lesion_grp_" + lesionGroupIndex + "_malignancy";
    });
    if (initialData) {
      const nums = (
        initialData.lesion_numbers ||
        (initialData.lesion_no != null ? [initialData.lesion_no] : [])
      ).slice();
      const numsInput = section.querySelector(".lesion-numbers-input");
      if (numsInput) numsInput.value = nums.join(", ");
      (initialData.dermatoscopic_features || []).forEach(function (f) {
        const c = section.querySelector('.lesion-feature[value="' + f + '"]');
        if (c) c.checked = true;
      });
      const cr = section.querySelector(
        '.lesion-clinical[value="' + (initialData.clinical_assessment || "UNREMARKABLE") + '"]'
      );
      if (cr) cr.checked = true;
      const mr = section.querySelector(
        '.lesion-malignancy[value="' + (initialData.malignancy_risk || "NO_SUSPICION") + '"]'
      );
      if (mr) mr.checked = true;
      const ta = section.querySelector(".lesion-text");
      if (ta && (initialData.edited_text || initialData.generated_text))
        ta.value = initialData.edited_text || initialData.generated_text || "";
    }
    const removeBtn = section.querySelector(".btn-remove-group");
    const lesionFavoriteSelect = section.querySelector(".lesion-favorite-select");
    const applyFavoriteBtn = section.querySelector(".btn-apply-lesion-favorite");
    const placeholder = UI.templateSelectPlaceholder;
    if (lesionFavoriteSelect) {
      const lesionOptions = lesionFavorites().map(function (fav, idx) {
        return { value: idx, label: fav.name || unnamedPresetLabel(idx) };
      });
      setSelectOptions(lesionFavoriteSelect, lesionOptions, placeholder);
    }
    if (applyFavoriteBtn && lesionFavoriteSelect) {
      applyFavoriteBtn.addEventListener("click", function () {
        const idx = parseInt(lesionFavoriteSelect.value, 10);
        if (isNaN(idx)) return;
        const favorite = lesionFavorites()[idx];
        if (!favorite) return;
        applyLesionFavorite(section, favorite);
        alertMsg(
          "success",
          UI.msgFavoriteApplied
        );
      });
    }
    if (removeBtn)
      removeBtn.addEventListener("click", function () {
        section.remove();
        reindexLesionGroups();
      });
    container.appendChild(frag);
    lesionGroupIndex++;
  }
  function reindexLesionGroups() {
    if (!hasLesionUi) return;
    const groups = container.querySelectorAll(".lesion-group");
    groups.forEach(function (section, i) {
      section.setAttribute("data-group-index", String(i));
      const titleEl = section.querySelector(".lesion-group-title");
      if (titleEl) titleEl.textContent = lesionGroupTitleLine(i);
      section.querySelectorAll(".lesion-clinical").forEach(function (r) {
        r.name = "lesion_grp_" + i + "_clinical";
      });
      section.querySelectorAll(".lesion-malignancy").forEach(function (r) {
        r.name = "lesion_grp_" + i + "_malignancy";
      });
    });
    lesionGroupIndex = groups.length;
  }

  const addBtn = el("btn-add-lesion-group");
  if (addBtn) addBtn.addEventListener("click", function () {
    addLesionGroup(null);
  });

  if (hasLesionUi && CTX && CTX.current_version && CTX.current_version.medical_payload) {
    const pl = CTX.current_version.medical_payload;
    (pl.examination_scope || []).forEach(function (v) {
      const c = document.querySelector(
        'input[name="examination_scope"][value="' + v + '"]'
      );
      if (c) c.checked = true;
    });
    const fp = document.querySelector(
      'input[name="fitzpatrick_type"][value="' + (pl.fitzpatrick_type || "") + '"]'
    );
    if (fp) fp.checked = true;
    const oa = document.querySelector(
      'input[name="overall_image_assessment"][value="' +
        (pl.overall_image_assessment || "NO_CONTROL_NEEDED") +
        '"]'
    );
    if (oa) oa.checked = true;
    (pl.recommendations || []).forEach(function (v) {
      const c = document.querySelector(
        'input[name="recommendations"][value="' + v + '"]'
      );
      if (c) c.checked = true;
    });
    const fa = document.querySelector(
      'input[name="final_assessment"][value="' +
        (pl.final_assessment || "NO_HIGH_GRADE_SUSPICION") +
        '"]'
    );
    if (fa) fa.checked = true;
    const summaryTextEl = el("summary_text");
    if (summaryTextEl) {
      if (pl.summary_edited_text) summaryTextEl.value = pl.summary_edited_text;
      else if (pl.summary_generated_text)
        summaryTextEl.value = pl.summary_generated_text;
    }
    const lesions = pl.lesions || [];
    if (lesions.length === 0) addLesionGroup(null);
    else lesions.forEach(function (l) {
      addLesionGroup(l);
    });
  } else if (hasLesionUi) {
    addLesionGroup(null);
  }

  function setSelectedTemplateById(templateId) {
    selectedTemplate = findTemplateById(templateId);
    refreshFavoriteSelects();
  }

  function loadDoctorTemplates() {
    if (!templateSelectEl) return Promise.resolve();
    const templateCtx =
      CTX &&
      CTX.current_version &&
      CTX.current_version.medical_payload &&
      CTX.current_version.medical_payload.template_context
        ? CTX.current_version.medical_payload.template_context
        : null;
    const currentTemplateId = templateCtx && templateCtx.template_id ? String(templateCtx.template_id) : "";
    const placeholder = UI.templateSelectPlaceholder;
    const localeUrl =
      API +
      "/doctor-text-templates?template_locale=" +
      encodeURIComponent(authoringLocale) +
      "&include_inactive=false";
    const fallbackUrl = API + "/doctor-text-templates?include_inactive=false";
    return apiFetch(localeUrl, { method: "GET" })
      .then(function (res) {
        if (!res.ok) throw new Error("template list failed");
        doctorTemplates = (res.json && res.json.results) || [];
        if (doctorTemplates.length === 0) {
          return apiFetch(fallbackUrl, { method: "GET" }).then(function (fallbackRes) {
            if (!fallbackRes.ok) throw new Error("template fallback failed");
            doctorTemplates = (fallbackRes.json && fallbackRes.json.results) || [];
          });
        }
      })
      .then(function () {
        const templateOptions = doctorTemplates.map(function (template) {
          return { value: template.id, label: template.name };
        });
        setSelectOptions(templateSelectEl, templateOptions, placeholder);
        if (currentTemplateId && findTemplateById(currentTemplateId)) {
          templateSelectEl.value = currentTemplateId;
          setSelectedTemplateById(currentTemplateId);
          return;
        }
        if (doctorTemplates.length > 0) {
          const firstId = String(doctorTemplates[0].id);
          templateSelectEl.value = firstId;
          setSelectedTemplateById(firstId);
          return;
        }
        selectedTemplate = null;
        refreshFavoriteSelects();
      })
      .catch(function () {
        doctorTemplates = [];
        selectedTemplate = null;
        refreshFavoriteSelects();
        alertMsg("warning", UI.msgTemplateLoadError);
      });
  }

  if (templateSelectEl) {
    templateSelectEl.addEventListener("change", function () {
      setSelectedTemplateById(this.value || "");
    });
  }
  if (applySummaryFavoriteBtn && summaryFavoriteSelectEl) {
    applySummaryFavoriteBtn.addEventListener("click", function () {
      const idx = parseInt(summaryFavoriteSelectEl.value, 10);
      if (isNaN(idx)) return;
      const favorite = summaryFavorites()[idx];
      if (!favorite) return;
      const summaryEl = el("summary_text");
      if (summaryEl) summaryEl.value = favorite.text || "";
      alertMsg(
        "success",
        UI.msgFavoriteApplied
      );
    });
  }
  loadDoctorTemplates();
  loadExternalPdfs();

  }

  function parseLesionNumbers(str) {
    if (!str || typeof str !== "string") return [];
    return str
      .split(/[\s,]+/)
      .map(function (s) {
        return parseInt(s.trim(), 10);
      })
      .filter(function (n) {
        return !isNaN(n) && n >= 1;
      });
  }

  function buildPayload() {
    const payload = {
      schema_version: 1,
      authoring_locale: authoringLocale,
      examination_scope: [],
      lesions: [],
      recommendations: [],
      final_assessment: "NO_HIGH_GRADE_SUSPICION",
    };
    document
      .querySelectorAll('input[name="examination_scope"]:checked')
      .forEach(function (c) {
        payload.examination_scope.push(c.value);
      });
    const fp = document.querySelector('input[name="fitzpatrick_type"]:checked');
    if (fp) payload.fitzpatrick_type = fp.value;
    const oa = document.querySelector(
      'input[name="overall_image_assessment"]:checked'
    );
    payload.overall_image_assessment = oa
      ? oa.value
      : "NO_CONTROL_NEEDED";
    document
      .querySelectorAll('input[name="final_assessment"]:checked')
      .forEach(function (c) {
        payload.final_assessment = c.value;
      });
    document
      .querySelectorAll('input[name="recommendations"]:checked')
      .forEach(function (c) {
        payload.recommendations.push(c.value);
      });
    const lesionContainer = el("lesion-groups-container");
    if (lesionContainer) {
      lesionContainer.querySelectorAll(".lesion-group").forEach(function (section) {
        const numsInput = section.querySelector(".lesion-numbers-input");
        const numsStr = numsInput ? numsInput.value : "";
        const lesion_numbers = parseLesionNumbers(numsStr);
        if (lesion_numbers.length === 0) return;
        const features = [];
        section
          .querySelectorAll(".lesion-feature:checked")
          .forEach(function (c) {
            features.push(c.value);
          });
        const clinical = section.querySelector(".lesion-clinical:checked");
        const malignancy = section.querySelector(".lesion-malignancy:checked");
        const textEl = section.querySelector(".lesion-text");
        const lesion = {
          lesion_numbers: lesion_numbers,
          dermatoscopic_features: features,
          clinical_assessment: clinical ? clinical.value : "UNREMARKABLE",
          malignancy_risk: malignancy ? malignancy.value : "NO_SUSPICION",
        };
        if (textEl && textEl.value) lesion.edited_text = textEl.value;
        payload.lesions.push(lesion);
      });
    }
    const summaryEl = el("summary_text");
    payload.summary_edited_text = summaryEl ? summaryEl.value || null : null;
    if (selectedTemplate) {
      payload.template_context = {
        template_id: selectedTemplate.id,
        template_name: selectedTemplate.name || null,
        template_locale: selectedTemplate.template_locale || authoringLocale,
      };
    }
    return payload;
  }

  function validatePayloadForSubmit(payload) {
    if (
      payload.overall_image_assessment === "CONTROL_NEEDED" &&
      (!payload.lesions || payload.lesions.length === 0)
    ) {
      return UI.msgLesionRequired;
    }
    return null;
  }

  function setBtnText(id, text) {
    var node = el(id);
    if (!node) return;
    node.textContent = text || "";
  }

  function setHiddenState(node, shouldHide) {
    if (!node) return;
    node.hidden = !!shouldHide;
    if (shouldHide) node.classList.add("hidden");
    else node.classList.remove("hidden");
  }

  function currentPublishedVersionNo() {
    if (publishedVersionNo != null) return publishedVersionNo;
    if (docStatus === "PUBLISHED" && CTX && CTX.current_version) {
      return CTX.current_version.version_no || "";
    }
    return "";
  }

  function revisionMessage(text) {
    return formatUiPlaceholders(text, {
      published_version_no: currentPublishedVersionNo(),
    });
  }

  function refreshRevisionUi() {
    var banner = el("revision-state-banner");
    var actionNotice = el("revision-action-notice");
    var publishedDocument = hasPublishedHistory();
    var publishedReadOnly =
      publishedDocument && !hasPendingRevision && !isPublicationRevoked();
    if (banner) {
      banner.classList.remove(
        "border-blue-200",
        "bg-blue-50",
        "text-blue-900",
        "dark:border-blue-800",
        "dark:bg-blue-950/40",
        "dark:text-blue-100",
        "border-amber-200",
        "bg-amber-50",
        "text-amber-900",
        "dark:border-amber-800",
        "dark:bg-amber-950/40",
        "dark:text-amber-100",
        "border-red-200",
        "bg-red-50",
        "text-red-900",
        "dark:border-red-800",
        "dark:bg-red-950/40",
        "dark:text-red-100"
      );
      banner.innerHTML = "";
      if (isPublicationRevoked()) {
        setHiddenState(banner, false);
        banner.classList.add(
          "border-red-200",
          "bg-red-50",
          "text-red-900",
          "dark:border-red-800",
          "dark:bg-red-950/40",
          "dark:text-red-100"
        );
        var titleRv = document.createElement("p");
        titleRv.className = "font-semibold mb-1";
        titleRv.textContent = UI.bannerRevokedTitle;
        var bodyRv = document.createElement("p");
        bodyRv.className = "mb-0";
        bodyRv.textContent = UI.bannerRevokedBody;
        banner.appendChild(titleRv);
        banner.appendChild(bodyRv);
      } else if (publishedReadOnly) {
        setHiddenState(banner, false);
        banner.classList.add(
          "border-blue-200",
          "bg-blue-50",
          "text-blue-900",
          "dark:border-blue-800",
          "dark:bg-blue-950/40",
          "dark:text-blue-100"
        );
        var titleP = document.createElement("p");
        titleP.className = "font-semibold mb-1";
        titleP.textContent = UI.bannerPublishedTitle;
        var bodyP = document.createElement("p");
        bodyP.className = "mb-0";
        bodyP.textContent = revisionMessage(UI.bannerPublishedBody);
        banner.appendChild(titleP);
        banner.appendChild(bodyP);
      } else if (publishedDocument && hasPendingRevision) {
        setHiddenState(banner, false);
        banner.classList.add(
          "border-amber-200",
          "bg-amber-50",
          "text-amber-900",
          "dark:border-amber-800",
          "dark:bg-amber-950/40",
          "dark:text-amber-100"
        );
        var titleP2 = document.createElement("p");
        titleP2.className = "font-semibold mb-1";
        titleP2.textContent = UI.bannerRevisionTitle;
        var bodyP2 = document.createElement("p");
        bodyP2.className = "mb-0";
        bodyP2.textContent = revisionMessage(UI.bannerRevisionBody);
        banner.appendChild(titleP2);
        banner.appendChild(bodyP2);
      } else {
        setHiddenState(banner, true);
      }
    }

    if (actionNotice) {
      actionNotice.classList.remove(
        "hidden",
        "border-blue-200",
        "bg-blue-50",
        "text-blue-900",
        "dark:border-blue-800",
        "dark:bg-blue-950/40",
        "dark:text-blue-100",
        "border-amber-200",
        "bg-amber-50",
        "text-amber-900",
        "dark:border-amber-800",
        "dark:bg-amber-950/40",
        "dark:text-amber-100",
        "border-red-200",
        "bg-red-50",
        "text-red-900",
        "dark:border-red-800",
        "dark:bg-red-950/40",
        "dark:text-red-100"
      );
      actionNotice.innerHTML = "";
      if (isPublicationRevoked()) {
        setHiddenState(actionNotice, false);
        actionNotice.classList.add(
          "border-red-200",
          "bg-red-50",
          "text-red-900",
          "dark:border-red-800",
          "dark:bg-red-950/40",
          "dark:text-red-100"
        );
        actionNotice.innerHTML =
          '<p class="mb-1 font-semibold">' +
          escapeHtml(UI.bannerRevokedTitle) +
          "</p>" +
          '<p class="mb-0">' +
          escapeHtml(UI.bannerRevokedBody) +
          "</p>";
      } else if (publishedReadOnly) {
        setHiddenState(actionNotice, false);
        actionNotice.classList.add(
          "border-blue-200",
          "bg-blue-50",
          "text-blue-900",
          "dark:border-blue-800",
          "dark:bg-blue-950/40",
          "dark:text-blue-100"
        );
        actionNotice.innerHTML =
          '<p class="mb-1 font-semibold">' +
          escapeHtml(UI.bannerPublishedTitle) +
          "</p>" +
          '<p class="mb-0">' +
          escapeHtml(revisionMessage(UI.bannerPublishedBody)) +
          "</p>";
      } else if (publishedDocument && hasPendingRevision) {
        setHiddenState(actionNotice, false);
        actionNotice.classList.add(
          "border-amber-200",
          "bg-amber-50",
          "text-amber-900",
          "dark:border-amber-800",
          "dark:bg-amber-950/40",
          "dark:text-amber-100"
        );
        actionNotice.innerHTML =
          '<p class="mb-1 font-semibold">' +
          escapeHtml(UI.bannerRevisionTitle) +
          "</p>" +
          '<p class="mb-0">' +
          escapeHtml(revisionMessage(UI.bannerRevisionBody)) +
          "</p>";
      } else {
        setHiddenState(actionNotice, true);
      }
    }

    var startBtn = el("btn-start-revision");
    var discardBtn = el("btn-discard-revision");
    var saveBtn = el("btn-save-draft");
    var publishBtnNode = el("btn-publish");
    var previewBtn = el("btn-preview-pdf");

    if (startBtn) {
      if (isPublicationRevoked()) {
        setHiddenState(startBtn, true);
        startBtn.disabled = true;
      } else if (publishedDocument) {
        setHiddenState(startBtn, false);
        startBtn.disabled = hasPendingRevision;
      } else {
        setHiddenState(startBtn, true);
        startBtn.disabled = false;
      }
    }
    if (discardBtn) {
      if (isPublicationRevoked()) {
        setHiddenState(discardBtn, true);
        discardBtn.disabled = true;
      } else if (publishedDocument) {
        setHiddenState(discardBtn, false);
        discardBtn.disabled = !hasPendingRevision;
      } else {
        setHiddenState(discardBtn, true);
        discardBtn.disabled = false;
      }
    }
    if (saveBtn) {
      saveBtn.classList.remove("hidden");
      saveBtn.disabled = false;
      setBtnText("btn-save-draft", UI.btnSaveDraft);
    }
    if (publishBtnNode) {
      publishBtnNode.classList.remove("hidden");
      publishBtnNode.textContent = publishedDocument
        ? UI.btnRepublish
        : UI.btnPublish;
    }
    if (previewBtn) {
      if (isPublicationRevoked()) {
        previewBtn.textContent = UI.btnPreviewPdf;
      } else if (publishedReadOnly) {
        previewBtn.textContent = UI.btnPreviewPublished;
      } else if (publishedDocument && hasPendingRevision) {
        previewBtn.textContent = UI.btnPreviewRevision;
      } else {
        previewBtn.textContent = UI.btnPreviewPdf;
      }
    }

    document.querySelectorAll(".js-btn-revoke-publication").forEach(function (revBtn) {
      var showRevoke =
        docStatus === "PUBLISHED" &&
        !hasPendingRevision &&
        !isPublicationRevoked() &&
        revokeDeliveryComplete();
      setHiddenState(revBtn, !showRevoke);
      revBtn.disabled = false;
    });

    setPublishEnabledFromPreviewFlag();
  }

  function showRevisionModal(opts) {
    return new Promise(function (resolve) {
      var modal = el("revision-modal");
      if (!modal) {
        resolve(false);
        return;
      }
      var titleEl = el("revision-modal-title");
      var bodyEl = el("revision-modal-body");
      var confirmBtn = el("revision-modal-confirm");
      var cancelBtn = el("revision-modal-cancel");
      if (titleEl) titleEl.textContent = opts.title || "";
      if (bodyEl) {
        bodyEl.textContent = revisionMessage(opts.body || "");
        bodyEl.className =
          "mt-2 text-sm leading-6 text-base-700 dark:text-base-300";
      }
      if (confirmBtn) confirmBtn.textContent = opts.confirm || "OK";
      if (cancelBtn) cancelBtn.textContent = opts.cancel || "Cancel";
      setHiddenState(modal, false);
      modal.classList.add("flex");

      function cleanup() {
        setHiddenState(modal, true);
        modal.classList.remove("flex");
        if (confirmBtn) confirmBtn.removeEventListener("click", onConfirm);
        if (cancelBtn) cancelBtn.removeEventListener("click", onCancel);
        modal.removeEventListener("click", onBackdrop);
      }
      function onConfirm() {
        cleanup();
        resolve(true);
      }
      function onCancel() {
        cleanup();
        resolve(false);
      }
      function onBackdrop(ev) {
        if (ev.target === modal) {
          cleanup();
          resolve(false);
        }
      }
      if (confirmBtn) confirmBtn.addEventListener("click", onConfirm);
      if (cancelBtn) cancelBtn.addEventListener("click", onCancel);
      modal.addEventListener("click", onBackdrop);
    });
  }

  function confirmStartRevision() {
    return showRevisionModal({
      title: UI.modalStartRevisionTitle,
      body: UI.modalStartRevisionBody,
      confirm: UI.modalStartRevisionConfirm,
      cancel: UI.modalStartRevisionCancel,
    });
  }

  function confirmDiscardRevision() {
    return showRevisionModal({
      title: UI.modalDiscardRevisionTitle,
      body: UI.modalDiscardRevisionBody,
      confirm: UI.modalDiscardRevisionConfirm,
      cancel: UI.modalStartRevisionCancel,
    });
  }

  function performStartRevisionAndSave() {
    var payload = buildPayload();
    var validationErr = validatePayloadForSubmit(payload);
    if (validationErr) {
      alertMsg("danger", validationErr);
      return;
    }
    var saveBtn = el("btn-save-draft");
    var startBtn = el("btn-start-revision");
    if (saveBtn) saveBtn.disabled = true;
    if (startBtn) startBtn.disabled = true;
    apiFetch(docUrl("/draft"), {
      method: "PUT",
      body: JSON.stringify({
        medical_payload_schema_version: 1,
        medical_payload: payload,
        intent: "amend",
      }),
    })
      .then(function (res) {
        if (saveBtn) saveBtn.disabled = false;
        if (startBtn) startBtn.disabled = false;
        if (isAuthExpiredResponse(res)) return;
        if (!res.ok) {
          alertMsg(
            "danger",
            responseErrorMessage(res, UI.msgError + " " + res.status)
          );
          return;
        }
        applyRevisionStateFromResponse(getResJson(res));
        previewSeenSinceLastSave = false;
        befundFormDirty = false;
        setPublishEnabledFromPreviewFlag();
        alertMsg("success", UI.msgRevisionStarted);
      })
      .catch(function () {
        if (saveBtn) saveBtn.disabled = false;
        if (startBtn) startBtn.disabled = false;
        alertMsg("danger", UI.msgNetwork);
      });
  }

  var startRevisionBtn = el("btn-start-revision");
  if (startRevisionBtn) {
    startRevisionBtn.addEventListener("click", function () {
      confirmStartRevision().then(function (confirmed) {
        if (!confirmed) return;
        performStartRevisionAndSave();
      });
    });
  }

  var discardRevisionBtn = el("btn-discard-revision");
  if (discardRevisionBtn) {
    discardRevisionBtn.addEventListener("click", function () {
      confirmDiscardRevision().then(function (confirmed) {
        if (!confirmed) return;
        discardRevisionBtn.disabled = true;
        apiFetch(docUrl("/discard-revision"), {
          method: "POST",
          body: JSON.stringify({}),
        })
          .then(function (res) {
            discardRevisionBtn.disabled = false;
            if (isAuthExpiredResponse(res)) return;
            if (res.status === 409) {
              var json409 = getResJson(res);
              if (
                json409 &&
                (json409.error_key ===
                  "other.api.no_pending_revision_to_discard" ||
                  json409.api_message_key ===
                    "other.api.no_pending_revision_to_discard")
              ) {
                alertMsg("warning", UI.msgNoPendingRevision);
                return;
              }
              alertMsg(
                "danger",
                (json409 && (json409.error || json409.detail)) ||
                  UI.msgError + " " + res.status
              );
              return;
            }
            if (!res.ok) {
              alertMsg(
                "danger",
                responseErrorMessage(res, UI.msgError + " " + res.status)
              );
              return;
            }
            applyRevisionStateFromResponse(getResJson(res));
            previewSeenSinceLastSave = true;
            setPublishEnabledFromPreviewFlag();
            alertMsg("success", UI.msgRevisionDiscarded);
          })
          .catch(function () {
            discardRevisionBtn.disabled = false;
            alertMsg("danger", UI.msgNetwork);
          });
      });
    });
  }

  refreshRevisionUi();
  setPublishEnabledFromPreviewFlag();

  function statusClass(status) {
    if (status === "COMPLETED") return "bg-success";
    if (status === "FAILED") return "bg-danger";
    if (status === "PROCESSING" || status === "PENDING") return "bg-warning text-dark";
    return "bg-secondary";
  }

  function setStatusBadge(id, status) {
    const badge = el(id);
    if (!badge) return;
    const safe = status || "—";
    badge.className = "badge " + statusClass(safe);
    badge.textContent = safe;
  }

  function renderProcessingStatus(currentVersion) {
    const cv = currentVersion || {};
    setStatusBadge("status-pdf", cv.pdf_generation_status || "—");
    setStatusBadge("status-hidrive", cv.hidrive_status || "—");
    setStatusBadge("status-sms", cv.sms_status || "—");

    const errorEl = el("processing-error");
    if (errorEl) {
      const msg = (cv.processing_error_message || "").trim();
      errorEl.textContent = msg;
      if (msg) errorEl.classList.remove("d-none");
      else errorEl.classList.add("d-none");
    }

    const retryBtn = el("btn-retry-processing");
    if (retryBtn) {
      if (cv.can_retry_processing) retryBtn.classList.remove("d-none");
      else retryBtn.classList.add("d-none");
    }
  }

  let refreshStatusInFlight = null;
  let refreshStatusCooldownUntil = 0;
  function refreshProcessingStatus(force) {
    const now = Date.now();
    if (!force && now < refreshStatusCooldownUntil) return Promise.resolve();
    if (refreshStatusInFlight) return refreshStatusInFlight;
    refreshStatusCooldownUntil = now + 1200;
    refreshStatusInFlight = apiFetch(docUrl("?form_locale=" + encodeURIComponent(authoringLocale)), {
      method: "GET",
    }).then(function (res) {
      if (isAuthExpiredResponse(res)) return;
      if (!res.ok) return;
      const updated = (res.json && res.json.current_version) || {};
      renderProcessingStatus(updated);
    }).finally(function () {
      refreshStatusInFlight = null;
    });
    return refreshStatusInFlight;
  }

  renderProcessingStatus(CTX.current_version || {});

  const refreshBtn = el("btn-refresh-status");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", function () {
      refreshProcessingStatus(true);
    });
  }

  const retryBtn = el("btn-retry-processing");
  if (retryBtn) {
    retryBtn.addEventListener("click", function () {
      retryBtn.disabled = true;
      apiFetch(docUrl("/retry-processing"), {
        method: "POST",
        body: JSON.stringify({ reason: "manual retry from doctor panel" }),
      })
        .then(function (res) {
          retryBtn.disabled = false;
          if (isAuthExpiredResponse(res)) return;
          if (!res.ok) {
            alertMsg("danger", responseErrorMessage(res, UI.msgError + " " + res.status));
            return;
          }
          alertMsg("success", UI.msgRetrySuccess);
          refreshProcessingStatus();
        })
        .catch(function () {
          retryBtn.disabled = false;
          alertMsg("danger", UI.msgNetwork);
        });
    });
  }

  function buildDraftPayloadBody() {
    const payload = buildPayload();
    const err = validatePayloadForSubmit(payload);
    if (err) return { error: err };
    const body = {
      medical_payload_schema_version: 1,
      medical_payload: payload,
    };
    if (docStatus === "PUBLISHED") {
      body.intent = "amend";
    } else {
      body.intent = "edit";
    }
    return { body: body };
  }

  function applyRevisionStateFromResponse(json) {
    if (!json) return;
    if (typeof json.document_status === "string" && json.document_status) {
      docStatus = json.document_status;
    }
    if (typeof json.has_pending_revision === "boolean") {
      hasPendingRevision = json.has_pending_revision;
    }
    if (typeof json.published_version_no !== "undefined") {
      publishedVersionNo = json.published_version_no;
    }
    refreshRevisionUi();
  }

  function getResJson(res) {
    return res && res.json ? res.json : null;
  }

  const saveDraftBtn = el("btn-save-draft");
  if (saveDraftBtn) {
    saveDraftBtn.addEventListener("click", function () {
      if (isPublishedReadOnly()) {
        confirmStartRevision().then(function (confirmed) {
          if (!confirmed) return;
          performStartRevisionAndSave();
        });
        return;
      }
      const built = buildDraftPayloadBody();
      if (built.error) {
        alertMsg("danger", built.error);
        return;
      }
      const btn = this;
      btn.disabled = true;
      apiFetch(docUrl("/draft"), {
        method: "PUT",
        body: JSON.stringify(built.body),
      })
        .then(function (res) {
          btn.disabled = false;
          if (isAuthExpiredResponse(res)) return;
          if (res.ok) {
            previewSeenSinceLastSave = false;
            befundFormDirty = false;
            applyRevisionStateFromResponse(getResJson(res));
            setPublishEnabledFromPreviewFlag();
            alertMsg("success", UI.msgSaveSuccess);
            return;
          }
          if (res.status === 409) {
            var json409s = getResJson(res);
            if (
              json409s &&
              (json409s.error_key === "other.api.amend_intent_required" ||
                json409s.api_message_key === "other.api.amend_intent_required")
            ) {
              alertMsg("warning", UI.msgAmendIntentRequired);
              return;
            }
            alertMsg(
              "danger",
              (json409s && (json409s.error || json409s.detail)) ||
                UI.msgError + " " + res.status
            );
            return;
          }
          alertMsg(
            "danger",
            responseErrorMessage(res, UI.msgError + " " + res.status)
          );
        })
        .catch(function () {
          btn.disabled = false;
          alertMsg("danger", UI.msgNetwork);
        });
    });
  }

  function buildPreviewUrl(source, previewBaseOverride) {
    const previewBase =
      previewBaseOverride ||
      (el("btn-preview-pdf") &&
        el("btn-preview-pdf").getAttribute("data-preview-url")) ||
      docUrl("/preview-pdf");
    const sep = previewBase.indexOf("?") === -1 ? "?" : "&";
    var url =
      previewBase +
      sep +
      "form_locale=" +
      encodeURIComponent(authoringLocale) +
      "&t=" +
      Date.now();
    if (source) {
      url += "&source=" + encodeURIComponent(source);
    }
    return url;
  }

  /**
   * Open PDF preview via full navigation (cookies sent). Prefer over fetch+blob when no
   * prior async work is required — some browsers leave a ``window.open('')`` tab on
   * ``about:blank`` after async fetch because navigation is no longer user-gesture gated.
   */
  function openPdfPreviewByFullNavigation(url) {
    window.open(url, "_blank", "noopener,noreferrer");
  }

  function openPreviewBlobInTab(previewTab, btn, previewUrl, opts) {
    return fetch(previewUrl, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/pdf" },
    }).then(function (pdfRes) {
      if (btn) btn.disabled = false;
      if (pdfRes.status === 401) {
        if (previewTab) previewTab.close();
        handleAuthExpired(UI.msgSessionExpired);
        return;
      }
      if (!pdfRes.ok) {
        if (previewTab) previewTab.close();
        var ct = (pdfRes.headers.get("content-type") || "").toLowerCase();
        if (ct.indexOf("application/json") !== -1) {
          return pdfRes.json().then(function (j) {
            alertMsg(
              "danger",
              (j && j.error) || UI.msgError + " " + pdfRes.status
            );
          });
        }
        alertMsg("danger", UI.msgError + " " + pdfRes.status);
        return;
      }
      var warn = pdfRes.headers.get("X-Befund-Preview-Warning");
      return pdfRes.blob().then(function (blob) {
        var objUrl = URL.createObjectURL(blob);
        if (previewTab) previewTab.location = objUrl;
        else window.location.href = objUrl;
        if (opts && opts.markPreviewSeen) {
          previewSeenSinceLastSave = true;
          setPublishEnabledFromPreviewFlag();
          alertMsg("success", UI.msgSaveSuccess);
        }
        if (warn) alertMsg("warning", UI.externalPdfPreviewMergeWarning);
      });
    });
  }

  const previewPdfBtn = el("btn-preview-pdf");
  if (previewPdfBtn) {
    previewPdfBtn.addEventListener("click", function (event) {
      if (event && event.preventDefault) event.preventDefault();
      const btn = this;
      if (PANEL.externalUploadReadOnly) {
        var extPreviewSource = null;
        if (isPublishedReadOnly()) {
          extPreviewSource = "published";
        } else if (docStatus === "PUBLISHED" && hasPendingRevision) {
          extPreviewSource = "draft";
        }
        openPdfPreviewByFullNavigation(
          buildPreviewUrl(
            extPreviewSource,
            btn.getAttribute("data-preview-url") || null
          )
        );
        return;
      }
      if (isPublishedReadOnly()) {
        openPdfPreviewByFullNavigation(buildPreviewUrl("published"));
        return;
      }
      const built = buildDraftPayloadBody();
      if (built.error) {
        alertMsg("danger", built.error);
        return;
      }
      const previewTab = window.open("", "_blank");
      btn.disabled = true;
      apiFetch(docUrl("/draft"), {
        method: "PUT",
        body: JSON.stringify(built.body),
      })
        .then(function (res) {
          if (isAuthExpiredResponse(res)) {
            btn.disabled = false;
            if (previewTab) previewTab.close();
            return;
          }
          if (!res.ok) {
            if (res.status === 409) {
              var json409p = getResJson(res);
              btn.disabled = false;
              if (previewTab) previewTab.close();
              if (
                json409p &&
                (json409p.error_key === "other.api.amend_intent_required" ||
                  json409p.api_message_key === "other.api.amend_intent_required")
              ) {
                alertMsg("warning", UI.msgAmendIntentRequired);
                return;
              }
              alertMsg(
                "danger",
                (json409p && (json409p.error || json409p.detail)) ||
                  UI.msgError + " " + res.status
              );
              return;
            }
            btn.disabled = false;
            alertMsg(
              "danger",
              responseErrorMessage(res, UI.msgError + " " + res.status)
            );
            if (previewTab) previewTab.close();
            return;
          }
          applyRevisionStateFromResponse(getResJson(res));
          befundFormDirty = false;
          return openPreviewBlobInTab(
            previewTab,
            btn,
            buildPreviewUrl("draft"),
            { markPreviewSeen: true }
          );
        })
        .catch(function () {
          btn.disabled = false;
          if (previewTab) previewTab.close();
          alertMsg("danger", UI.msgNetwork);
        });
    });
  }

  const previewPublishedExternalBtn = el("btn-preview-published-external");
  if (previewPublishedExternalBtn) {
    previewPublishedExternalBtn.addEventListener("click", function (event) {
      if (event && event.preventDefault) event.preventDefault();
      var baseOverride =
        this.getAttribute("data-preview-url") ||
        (el("btn-preview-pdf") &&
          el("btn-preview-pdf").getAttribute("data-preview-url")) ||
        null;
      openPdfPreviewByFullNavigation(
        buildPreviewUrl("published", baseOverride)
      );
    });
  }

  const publishBtn = el("btn-publish");
  if (publishBtn) {
    publishBtn.addEventListener("click", function () {
      if (isPublishedReadOnly()) {
        return;
      }
      if (!previewSeenSinceLastSave) {
        alertMsg("warning", UI.msgPublishPreviewRequired);
        return;
      }
      const built = buildDraftPayloadBody();
      if (built.error) {
        alertMsg("danger", built.error);
        return;
      }
      const resendSmsEl = el("resend_sms");
      const resendSms = resendSmsEl ? resendSmsEl.checked : false;
      publishBtn.disabled = true;
      const publishId = crypto.randomUUID
        ? crypto.randomUUID()
        : "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/x/g, function () {
            return (Math.random() * 16 | 0).toString(16);
          });
      apiFetch(docUrl("/draft"), {
        method: "PUT",
        body: JSON.stringify(built.body),
      })
        .then(function (res) {
          if (isAuthExpiredResponse(res)) {
            publishBtn.disabled = false;
            return;
          }
          if (!res.ok) {
            if (res.status === 409) {
              var json409pub = getResJson(res);
              publishBtn.disabled = false;
              if (
                json409pub &&
                (json409pub.error_key === "other.api.amend_intent_required" ||
                  json409pub.api_message_key === "other.api.amend_intent_required")
              ) {
                alertMsg("warning", UI.msgAmendIntentRequired);
                return;
              }
              alertMsg(
                "danger",
                (json409pub && (json409pub.error || json409pub.detail)) ||
                  UI.msgError + " " + res.status
              );
              return;
            }
            publishBtn.disabled = false;
            alertMsg(
              "danger",
              responseErrorMessage(res, UI.msgError + " " + res.status)
            );
            return;
          }
          befundFormDirty = false;
          return apiFetch(
            docUrl("/publish"),
            {
              method: "POST",
              body: JSON.stringify({
                publish_request_id: publishId,
                resend_sms: resendSms,
                publish_locale: authoringLocale,
              }),
            }
          );
        })
        .then(function (res) {
          if (!res) return;
          if (isAuthExpiredResponse(res)) {
            publishBtn.disabled = false;
            return;
          }
          if (res.ok) {
            alertMsg("success", UI.msgPublishSuccess);
            publishBtn.disabled = true;
            befundFormDirty = false;
            // Server publish clears the lock; still release client-side before leave.
            releaseEditLockBestEffort();
            var listUrl =
              (PANEL && PANEL.listUrl) ||
              (function () {
                var pathname = window.location.pathname || "";
                var listPath = pathname.replace(/\/[^/]+\/?$/, "/") || "/doctor/";
                return window.location.origin + listPath;
              })();
            setTimeout(function () {
              window.location.href = listUrl;
            }, 1200);
          } else {
            publishBtn.disabled = false;
            alertMsg(
              "danger",
              responseErrorMessage(res, UI.msgError + " " + res.status)
            );
          }
        })
        .catch(function () {
          publishBtn.disabled = false;
          alertMsg("danger", UI.msgNetwork);
        });
    });
  }

  document.body.addEventListener("click", function (ev) {
    var btn =
      ev.target &&
      ev.target.closest &&
      ev.target.closest(".js-btn-revoke-publication");
    if (!btn || btn.disabled || btn.hidden) return;
    ev.preventDefault();
    showRevisionModal({
      title: UI.modalRevokePublicationTitle,
      body: UI.modalRevokePublicationBody,
      confirm: UI.modalRevokePublicationConfirm,
      cancel: UI.modalRevokePublicationCancel,
    }).then(function (ok) {
      if (!ok) return;
      btn.disabled = true;
      apiFetch(docUrl("/revoke"), {
        method: "POST",
        body: JSON.stringify({}),
      })
        .then(function (res) {
          btn.disabled = false;
          if (isAuthExpiredResponse(res)) return;
          if (!res.ok) {
            alertMsg(
              "danger",
              responseErrorMessage(res, UI.msgError + " " + res.status)
            );
            return;
          }
          alertMsg("success", UI.msgRevokePublicationSuccess);
          window.location.reload();
        })
        .catch(function () {
          btn.disabled = false;
          alertMsg("danger", UI.msgNetwork);
        });
    });
  });
})();
