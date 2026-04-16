/**
 * Tablet intake form – consents, body map, anamnesis, signature, submit.
 * Expects: window.__TABLET_FORM_CONFIG__ and script#body-map-initial, script#form-ui.
 */
(function () {
  "use strict";

  const config = window.__TABLET_FORM_CONFIG__;
  if (!config) return;

  const formId = config.formId;
  const apiBase = config.apiBase || "/api/v1";
  const schemaVersion = config.schemaVersion;
  const bodyMapSchemaVersion = config.bodyMapSchemaVersion;
  /** True after signature was saved to server (or was already saved on load). Required before submit. */
  let signatureSaved = Boolean(config.hasSignature);
  let intakeSubmitInProgress = false;
  let autoSubmitAfterSignatureTimer = null;
  const AUTO_SUBMIT_AFTER_SIGNATURE_MS = 60 * 1000;

  const bodyMapInitialEl = document.getElementById("body-map-initial");
  const formUiEl = document.getElementById("form-ui");
  const initialBodyMapData = bodyMapInitialEl
    ? JSON.parse(bodyMapInitialEl.textContent || "[]")
    : [];
  const formUi = formUiEl ? JSON.parse(formUiEl.textContent || "{}") : {};

  function getCsrfToken() {
    const el = document.querySelector("[name=csrfmiddlewaretoken]");
    return el
      ? el.value
      : (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || "";
  }

  function api(method, path, body) {
    const opts = {
      method,
      credentials: "same-origin",
      headers: {
        "X-CSRFToken": getCsrfToken(),
        "Content-Type": "application/json",
      },
    };
    if (body) opts.body = JSON.stringify(body);
    return fetch(apiBase + path, opts);
  }

  function showMsg(id, text, isError) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.className = isError ? "error" : "success";
    el.style.display = text ? "block" : "none";
  }

  function clearConsentBlockMsgs() {
    document
      .querySelectorAll("#consents-section .consent-block-msg")
      .forEach(function (el) {
        el.textContent = "";
        el.className = "consent-block-msg";
        el.style.display = "none";
      });
  }

  function showConsentBlockMsg(block, text, isError) {
    const msgEl = block && block.querySelector(".consent-block-msg");
    if (!msgEl) return;
    msgEl.textContent = text || "";
    if (text) {
      msgEl.className =
        "consent-block-msg " + (isError === false ? "success" : "error");
      msgEl.style.display = "block";
    } else {
      msgEl.className = "consent-block-msg";
      msgEl.style.display = "none";
    }
  }

  function findFirstInvalidRequiredConsentBlock(consentBlocks) {
    let first = null;
    consentBlocks.forEach(function (block) {
      if (first) return;
      if (block.dataset.required !== "true") return;
      const multiCheckboxes = block.querySelectorAll(
        'input[name="multi-consent"]'
      );
      if (multiCheckboxes.length > 0) {
        const selected = block.querySelectorAll(
          'input[name="multi-consent"]:checked'
        );
        if (!selected.length) first = block;
        return;
      }
      const cb = block.querySelector('input[name="consent"]');
      if (!cb || !cb.checked) first = block;
    });
    return first;
  }

  function firstConsentBlockForServerMessage() {
    return document.querySelector("#consents-section .consent-block");
  }

  function clearAnamnesisFieldMsgs() {
    document
      .querySelectorAll("#anamnesis-section .anamnesis-field-msg")
      .forEach(function (el) {
        el.textContent = "";
        el.className = "anamnesis-field-msg";
        el.style.display = "none";
      });
  }

  function showAnamnesisFieldMsg(block, text, isError) {
    const msgEl = block && block.querySelector(".anamnesis-field-msg");
    if (!msgEl) return;
    msgEl.textContent = text || "";
    if (text) {
      msgEl.className =
        "anamnesis-field-msg " + (isError === false ? "success" : "error");
      msgEl.style.display = "block";
    } else {
      msgEl.className = "anamnesis-field-msg";
      msgEl.style.display = "none";
    }
  }

  function firstAnamnesisFieldForServerMessage() {
    return document.querySelector("#anamnesis-section .field");
  }

  function showConnectionError() {
    const banner = document.getElementById("tablet-form-connection-error");
    if (banner) {
      banner.classList.add("visible");
      const text = banner.querySelector(".tablet-form-connection-error-text");
      if (text) text.textContent = formUi.msg_connection_error || "";
    }
  }

  function hideConnectionError() {
    const banner = document.getElementById("tablet-form-connection-error");
    if (banner) banner.classList.remove("visible");
  }

  function clearAutoSubmitAfterSignatureTimer() {
    if (autoSubmitAfterSignatureTimer !== null) {
      clearTimeout(autoSubmitAfterSignatureTimer);
      autoSubmitAfterSignatureTimer = null;
    }
    const hint = document.getElementById("auto-submit-hint");
    if (hint) {
      hint.textContent = "";
      hint.style.display = "none";
    }
  }

  function scheduleAutoSubmitAfterSignature() {
    clearAutoSubmitAfterSignatureTimer();
    if (!signatureSaved) return;
    const step3 = document.getElementById("step-3");
    if (!step3 || !step3.classList.contains("active")) return;
    const hint = document.getElementById("auto-submit-hint");
    const hintText =
      formUi.msg_auto_submit_after_signature ||
      "If you take no action, the form will be submitted automatically in one minute.";
    if (hint) {
      hint.textContent = hintText;
      hint.style.display = "block";
    }
    autoSubmitAfterSignatureTimer = setTimeout(function () {
      autoSubmitAfterSignatureTimer = null;
      if (hint) {
        hint.textContent = "";
        hint.style.display = "none";
      }
      if (!signatureSaved || intakeSubmitInProgress) return;
      const step3c = document.getElementById("step-3");
      if (!step3c || !step3c.classList.contains("active")) return;
      performIntakeSubmit();
    }, AUTO_SUBMIT_AFTER_SIGNATURE_MS);
  }

  function performIntakeSubmit() {
    const btn = document.getElementById("submit-form");
    if (!signatureSaved) {
      showMsg(
        "submit-msg",
        formUi.msg_signature_required_before_submit ||
          "Signature is required before submitting.",
        true
      );
      return;
    }
    if (intakeSubmitInProgress) return;
    intakeSubmitInProgress = true;
    clearAutoSubmitAfterSignatureTimer();
    if (btn) btn.disabled = true;
    hideConnectionError();
    api("POST", "/intake-forms/" + formId + "/submit", {})
      .then(function (r) {
        if (r.ok) {
          window.location.href = "/tablet/form/" + formId + "/";
        } else {
          intakeSubmitInProgress = false;
          r
            .json()
            .catch(function () {
              return {};
            })
            .then(function (d) {
              showMsg(
                "submit-msg",
                d.error || formUi.msg_submit_error || "",
                true
              );
              if (btn) btn.disabled = false;
              if (signatureSaved) scheduleAutoSubmitAfterSignature();
            });
        }
      })
      .catch(function () {
        intakeSubmitInProgress = false;
        showMsg("submit-msg", formUi.msg_connection_error || "", true);
        if (btn) btn.disabled = false;
        showConnectionError();
        if (signatureSaved) scheduleAutoSubmitAfterSignature();
      });
  }

  const stepTitles = [
    formUi.step_1_title,
    formUi.step_2_title,
    formUi.step_3_title,
  ];

  function getFocusTargetForStep(stepNum) {
    const stepEl = document.getElementById("step-" + stepNum);
    if (!stepEl) return null;
    const focusable =
      stepEl.querySelector(
        'input:not([disabled]), button:not([disabled]), [tabindex="0"]'
      ) ||
      stepEl.querySelector(".step-actions button");
    return focusable;
  }

  function updateStepper(currentStep) {
    const dots = document.querySelectorAll(".tablet-form-stepper .stepper-dot");
    const lines = document.querySelectorAll(".tablet-form-stepper .stepper-line");
    dots.forEach(function (dot, i) {
      const step = i + 1;
      dot.classList.remove("current", "done");
      dot.setAttribute("aria-current", step === currentStep ? "step" : "false");
      if (step === currentStep) dot.classList.add("current");
      else if (step < currentStep) dot.classList.add("done");
    });
    lines.forEach(function (line, i) {
      line.classList.toggle("done", i + 1 < currentStep);
    });
  }

  function goToStep(stepNum) {
    const prevActive = document.querySelector(".form-step.active");
    document
      .querySelectorAll(".form-step")
      .forEach(function (el) {
        el.classList.remove("active");
        el.setAttribute("aria-hidden", "true");
      });
    const stepEl = document.getElementById("step-" + stepNum);
    if (stepEl) {
      stepEl.classList.add("active");
      stepEl.setAttribute("aria-hidden", "false");
    }
    const ind = document.getElementById("step-indicator");
    if (ind && stepTitles[stepNum - 1]) ind.textContent = stepTitles[stepNum - 1];
    updateStepper(stepNum);
    if (stepNum === 3 && typeof initCanvas === "function") {
      requestAnimationFrame(function () {
        initCanvas();
      });
    }
    window.scrollTo(0, 0);
    const focusTarget = getFocusTargetForStep(stepNum);
    if (focusTarget) {
      requestAnimationFrame(function () {
        focusTarget.focus();
      });
    }
    if (window.history && window.history.replaceState) {
      var base = window.location.pathname + window.location.search;
      window.history.replaceState(null, "", base + "#step-" + stepNum);
    } else {
      window.location.hash = "#step-" + stepNum;
    }
    updateLanguageLinksHash();
    if (stepNum === 3 && signatureSaved) {
      scheduleAutoSubmitAfterSignature();
    } else {
      clearAutoSubmitAfterSignatureTimer();
    }
    if (prevActive && prevActive.id === "step-2" && stepNum !== 2) {
      clearAnamnesisFieldMsgs();
    }
  }

  function updateLanguageLinksHash() {
    var hash = window.location.hash || "";
    document.querySelectorAll('a[href^="?locale="]').forEach(function (a) {
      var href = a.getAttribute("href") || "";
      a.setAttribute("href", href.split("#")[0] + hash);
    });
  }

  let bodyMapPoints = Array.isArray(initialBodyMapData)
    ? initialBodyMapData.slice()
    : [];
  const bodyMapWrap = document.getElementById("body-map-wrap");
  const bodyMapImg = document.getElementById("body-map-img");
  const bodyMapMarkersEl = document.getElementById("body-map-markers");

  function renderBodyMapMarkers() {
    if (!bodyMapMarkersEl) return;
    bodyMapMarkersEl.innerHTML = "";
    const undoLastPointBtn = document.getElementById("body-map-undo-last");
    if (undoLastPointBtn) undoLastPointBtn.disabled = bodyMapPoints.length === 0;
    bodyMapPoints.forEach(function (p, i) {
      const div = document.createElement("div");
      div.className = "body-map-marker";
      div.style.left = p.x * 100 + "%";
      div.style.top = p.y * 100 + "%";
      div.setAttribute("data-index", String(i));
      div.setAttribute("title", formUi.body_map_undo_last || "Cofnij punkt");
      div.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        const idx = parseInt(div.getAttribute("data-index"), 10);
        if (!isNaN(idx) && idx >= 0 && idx < bodyMapPoints.length) {
          bodyMapPoints.splice(idx, 1);
          renderBodyMapMarkers();
        }
      });
      bodyMapMarkersEl.appendChild(div);
    });
  }

  if (bodyMapImg) {
    bodyMapImg.addEventListener("click", function (e) {
      const rect = bodyMapImg.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width;
      const y = (e.clientY - rect.top) / rect.height;
      const side = x < 0.5 ? "front" : "back";
      bodyMapPoints.push({
        x: Math.round(x * 1000) / 1000,
        y: Math.round(y * 1000) / 1000,
        side: side,
      });
      renderBodyMapMarkers();
    });
  }

  const undoLastPointBtn = document.getElementById("body-map-undo-last");
  if (undoLastPointBtn) {
    undoLastPointBtn.addEventListener("click", function () {
      if (bodyMapPoints.length > 0) {
        bodyMapPoints.pop();
        renderBodyMapMarkers();
      }
    });
  }

  const saveBodyMapBtn = document.getElementById("save-body-map");
  if (saveBodyMapBtn) {
    saveBodyMapBtn.addEventListener("click", function () {
      hideConnectionError();
      api("PATCH", "/intake-forms/" + formId, {
        body_map_schema_version: bodyMapSchemaVersion,
        body_map_data: bodyMapPoints,
      })
        .then(function (r) {
          if (r.ok)
            showMsg("body-map-msg", formUi.msg_body_map_saved || "", false);
          else
            r
              .json()
              .catch(function () { return {}; })
              .then(function (d) {
                showMsg(
                  "body-map-msg",
                  d.error || formUi.msg_save_error || "",
                  true
                );
              });
        })
        .catch(function () {
          showMsg("body-map-msg", formUi.msg_connection_error || "", true);
          showConnectionError();
        });
    });
  }

  renderBodyMapMarkers();

  const btnStep1Next = document.getElementById("btn-step1-next");
  if (btnStep1Next) {
    btnStep1Next.addEventListener("click", function () {
      const consentBlocks = document.querySelectorAll(
        "#consents-section .consent-block"
      );
      const firstInvalid =
        findFirstInvalidRequiredConsentBlock(consentBlocks);
      if (firstInvalid) {
        clearConsentBlockMsgs();
        showConsentBlockMsg(
          firstInvalid,
          formUi.validation_consents_required ||
            "Bitte alle Pflichtfelder ausfüllen.",
          true
        );
        requestAnimationFrame(function () {
          const focusEl =
            firstInvalid.querySelector('input[name="consent"]') ||
            firstInvalid.querySelector('input[name="multi-consent"]');
          firstInvalid.scrollIntoView({
            behavior: "smooth",
            block: "center",
          });
          if (focusEl) focusEl.focus({ preventScroll: true });
        });
        return;
      }
      clearConsentBlockMsgs();
      hideConnectionError();
      const consents = [];
      consentBlocks.forEach(function (block) {
        const consentId = block.dataset.consentId;
        const multiCheckboxes = block.querySelectorAll('input[name="multi-consent"]');
        
        if (multiCheckboxes.length > 0) {
          const selected = block.querySelectorAll('input[name="multi-consent"]:checked');
          const selectedCodes = [];
          selected.forEach(function (el) {
            selectedCodes.push(el.value);
          });
          const payload = {
            consent_definition_id: consentId,
            accepted: selectedCodes.length > 0,
          };
          if (selectedCodes.length) payload.selected_option_codes = selectedCodes;
          consents.push(payload);
          return;
        }

        const cb = block.querySelector('input[name="consent"]');
        consents.push({
          consent_definition_id: consentId,
          accepted: Boolean(cb && cb.checked),
        });
      });
      api("PUT", "/intake-forms/" + formId + "/consents", { consents })
        .then(function (r) {
          if (r.ok) {
            goToStep(2);
          } else {
            r
              .json()
              .then(function (d) {
                clearConsentBlockMsgs();
                const target = firstConsentBlockForServerMessage();
                if (target) {
                  showConsentBlockMsg(
                    target,
                    d.error || formUi.msg_save_error || "",
                    true
                  );
                  target.scrollIntoView({
                    behavior: "smooth",
                    block: "center",
                  });
                }
              });
          }
        })
        .catch(function () {
          clearConsentBlockMsgs();
          const target = firstConsentBlockForServerMessage();
          if (target) {
            showConsentBlockMsg(
              target,
              formUi.msg_connection_error || "",
              true
            );
            target.scrollIntoView({
              behavior: "smooth",
              block: "center",
            });
          }
          showConnectionError();
        });
    });
  }

  const consentsSectionEl = document.getElementById("consents-section");
  if (consentsSectionEl) {
    consentsSectionEl.addEventListener("change", function (e) {
      const t = e.target;
      if (!t || (t.name !== "consent" && t.name !== "multi-consent")) return;
      const block = t.closest(".consent-block");
      if (block) showConsentBlockMsg(block, "", true);
    });
  }

  const anamnesisSectionEl = document.getElementById("anamnesis-section");
  if (anamnesisSectionEl) {
    anamnesisSectionEl.addEventListener("change", function (e) {
      const t = e.target;
      if (!t) return;
      if (t.type !== "radio" && t.type !== "checkbox") return;
      const block = t.closest(".field");
      if (block) showAnamnesisFieldMsg(block, "", true);
    });
    anamnesisSectionEl.addEventListener("input", function (e) {
      const t = e.target;
      if (!t || t.type !== "text") return;
      if (!t.name || t.name.indexOf("q-text-") !== 0) return;
      const block = t.closest(".field");
      if (block) showAnamnesisFieldMsg(block, "", true);
    });
  }

  document
    .getElementById("btn-step2-back")
    .addEventListener("click", function () {
      goToStep(1);
    });
  document
    .getElementById("btn-step3-back")
    .addEventListener("click", function () {
      goToStep(2);
    });

  function isAnamnesisRequiredAnswered(block) {
    const radios = block.querySelectorAll('input[type="radio"]:checked');
    const checks = block.querySelectorAll('input[type="checkbox"]:checked');
    const textInput = block.querySelector('input[type="text"]');
    const hasText = textInput && textInput.value.trim().length > 0;
    return radios.length > 0 || checks.length > 0 || hasText;
  }

  function findFirstInvalidRequiredAnamnesisField() {
    const requiredQuestions = document.querySelectorAll(
      '#anamnesis-section .field[data-required="true"]'
    );
    var i;
    for (i = 0; i < requiredQuestions.length; i++) {
      if (!isAnamnesisRequiredAnswered(requiredQuestions[i])) {
        return requiredQuestions[i];
      }
    }
    return null;
  }

  const btnStep2Next = document.getElementById("btn-step2-next");
  if (btnStep2Next) {
    btnStep2Next.addEventListener("click", function () {
      showMsg("body-map-msg", "", false);
      clearAnamnesisFieldMsgs();
      const firstInvalid = findFirstInvalidRequiredAnamnesisField();
      if (firstInvalid) {
        showAnamnesisFieldMsg(
          firstInvalid,
          formUi.validation_anamnesis_required ||
            "Bitte alle Pflichtfragen beantworten.",
          true
        );
        requestAnimationFrame(function () {
          const focusEl =
            firstInvalid.querySelector('input[type="radio"]') ||
            firstInvalid.querySelector('input[type="checkbox"]') ||
            firstInvalid.querySelector('input[type="text"]');
          firstInvalid.scrollIntoView({
            behavior: "smooth",
            block: "center",
          });
          if (focusEl) focusEl.focus({ preventScroll: true });
        });
        return;
      }
      hideConnectionError();
      const bodyMapPromise = api("PATCH", "/intake-forms/" + formId, {
        body_map_schema_version: bodyMapSchemaVersion,
        body_map_data: bodyMapPoints,
      });
      const answers = [];
      document
        .querySelectorAll("#anamnesis-section [data-question-code]")
        .forEach(function (block) {
          const code = block.dataset.questionCode;
          const radios = block.querySelectorAll('input[type="radio"]:checked');
          const checks = block.querySelectorAll('input[type="checkbox"]:checked');
          const textInput = block.querySelector('input[type="text"]');
          const selected_option_codes = [];
          radios.forEach(function (r) {
            selected_option_codes.push(r.value);
          });
          checks.forEach(function (c) {
            selected_option_codes.push(c.value);
          });
          const free_text = textInput ? textInput.value.trim() : null;
          answers.push({
            question_code: code,
            selected_option_codes: selected_option_codes,
            free_text: free_text || null,
          });
        });
      const anamnesisPromise = api("PUT", "/intake-forms/" + formId + "/anamnesis", {
        anamnesis_schema_version: schemaVersion,
        answers: answers,
      });
      Promise.all([bodyMapPromise, anamnesisPromise])
        .then(function (results) {
          const r1 = results[0],
            r2 = results[1];
          if (r1.ok && r2.ok) {
            clearAnamnesisFieldMsgs();
            goToStep(3);
          } else {
            if (!r1.ok)
              r1.json().catch(function () { return {}; }).then(function (d) {
                showMsg(
                  "body-map-msg",
                  d.error || formUi.msg_save_error || "",
                  true
                );
              });
            if (!r2.ok)
              r2.json().catch(function () { return {}; }).then(function (d) {
                clearAnamnesisFieldMsgs();
                const target = firstAnamnesisFieldForServerMessage();
                if (target) {
                  showAnamnesisFieldMsg(
                    target,
                    d.error || formUi.msg_save_error || "",
                    true
                  );
                  target.scrollIntoView({
                    behavior: "smooth",
                    block: "center",
                  });
                }
              });
          }
        })
        .catch(function () {
          clearAnamnesisFieldMsgs();
          const target = firstAnamnesisFieldForServerMessage();
          if (target) {
            showAnamnesisFieldMsg(
              target,
              formUi.msg_connection_error || "",
              true
            );
            target.scrollIntoView({
              behavior: "smooth",
              block: "center",
            });
          }
          showConnectionError();
        });
    });
  }

  const saveAnamnesisEl = document.getElementById("save-anamnesis");
  if (saveAnamnesisEl) {
    saveAnamnesisEl.addEventListener("click", function () {
      hideConnectionError();
      const answers = [];
      document
        .querySelectorAll("#anamnesis-section [data-question-code]")
        .forEach(function (block) {
          const code = block.dataset.questionCode;
          const radios = block.querySelectorAll('input[type="radio"]:checked');
          const checks = block.querySelectorAll('input[type="checkbox"]:checked');
          const textInput = block.querySelector('input[type="text"]');
          const selected_option_codes = [];
          radios.forEach(function (r) {
            selected_option_codes.push(r.value);
          });
          checks.forEach(function (c) {
            selected_option_codes.push(c.value);
          });
          const free_text = textInput ? textInput.value.trim() : null;
          answers.push({
            question_code: code,
            selected_option_codes: selected_option_codes,
            free_text: free_text || null,
          });
        });
      api("PUT", "/intake-forms/" + formId + "/anamnesis", {
        anamnesis_schema_version: schemaVersion,
        answers: answers,
      })
        .then(function (r) {
          if (r.ok) {
            clearAnamnesisFieldMsgs();
            const okTarget = firstAnamnesisFieldForServerMessage();
            if (okTarget) {
              showAnamnesisFieldMsg(
                okTarget,
                formUi.msg_anamnesis_saved || "",
                false
              );
            }
          } else {
            r
              .json()
              .catch(function () { return {}; })
              .then(function (d) {
                clearAnamnesisFieldMsgs();
                const target = firstAnamnesisFieldForServerMessage();
                if (target) {
                  showAnamnesisFieldMsg(
                    target,
                    d.error || formUi.msg_save_error || "",
                    true
                  );
                  target.scrollIntoView({
                    behavior: "smooth",
                    block: "center",
                  });
                }
              });
          }
        })
        .catch(function () {
          clearAnamnesisFieldMsgs();
          const target = firstAnamnesisFieldForServerMessage();
          if (target) {
            showAnamnesisFieldMsg(
              target,
              formUi.msg_connection_error || "",
              true
            );
            target.scrollIntoView({
              behavior: "smooth",
              block: "center",
            });
          }
          showConnectionError();
        });
    });
  }

  var initCanvas;
  (function () {
    const canvas = document.getElementById("signatureCanvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    let drawing = false;
    /** True after user drew at least one stroke; reset on clear or canvas resize. */
    let hasDrawn = false;

    initCanvas = function () {
      var w = canvas.clientWidth || 560;
      var h = canvas.clientHeight || 240;
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
        hasDrawn = false;
        ctx.strokeStyle = "#000";
        ctx.lineWidth = 2;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
      }
    };
    initCanvas();
    window.addEventListener("resize", initCanvas);

    function getPos(e) {
      const rect = canvas.getBoundingClientRect();
      const x =
        e.clientX != null
          ? e.clientX
          : e.touches && e.touches[0]
            ? e.touches[0].clientX
            : 0;
      const y =
        e.clientY != null
          ? e.clientY
          : e.touches && e.touches[0]
            ? e.touches[0].clientY
            : 0;
      const dx = x - rect.left;
      const dy = y - rect.top;
      const scaleX = rect.width > 0 ? canvas.width / rect.width : 1;
      const scaleY = rect.height > 0 ? canvas.height / rect.height : 1;
      return { x: dx * scaleX, y: dy * scaleY };
    }

    function onPointerDown(e) {
      e.preventDefault();
      drawing = true;
      canvas.setPointerCapture(e.pointerId);
      const p = getPos(e);
      ctx.beginPath();
      ctx.moveTo(p.x, p.y);
    }
    function onPointerMove(e) {
      if (!drawing) return;
      e.preventDefault();
      const p = getPos(e);
      ctx.lineTo(p.x, p.y);
      ctx.stroke();
      hasDrawn = true;
    }
    function onPointerUp(e) {
      e.preventDefault();
      try {
        canvas.releasePointerCapture(e.pointerId);
      } catch (_) {}
      drawing = false;
    }

    canvas.addEventListener("pointerdown", onPointerDown, { passive: false });
    canvas.addEventListener("pointermove", onPointerMove, { passive: false });
    canvas.addEventListener("pointerup", onPointerUp, { passive: false });
    canvas.addEventListener("pointerleave", onPointerUp, { passive: false });
    canvas.addEventListener("pointercancel", onPointerUp, { passive: false });

    const clearBtn = document.getElementById("clear-signature");
    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        hasDrawn = false;
        signatureSaved = false;
        const savedEl = document.getElementById("signature-saved");
        if (savedEl) savedEl.style.display = "none";
        const submitBtn = document.getElementById("submit-form");
        if (submitBtn) submitBtn.disabled = true;
        showMsg("signature-msg", "", false);
        clearAutoSubmitAfterSignatureTimer();
      });
    }

    const saveSigBtn = document.getElementById("save-signature");
    if (saveSigBtn) {
      saveSigBtn.addEventListener("click", function () {
        hideConnectionError();
        if (!hasDrawn) {
          showMsg("signature-msg", formUi.msg_signature_draw_first || "Please draw your signature first.", true);
          return;
        }
        const dataUrl = canvas.toDataURL("image/png");
        api("POST", "/intake-forms/" + formId + "/signature", {
          signature_base64: dataUrl,
        })
          .then(function (r) {
            if (r.ok) {
              signatureSaved = true;
              const savedEl = document.getElementById("signature-saved");
              if (savedEl) savedEl.style.display = "inline";
              const submitBtn = document.getElementById("submit-form");
              if (submitBtn) submitBtn.disabled = false;
              showMsg("signature-msg", "", false);
              scheduleAutoSubmitAfterSignature();
            } else {
              r
                .json()
                .catch(function () { return {}; })
                .then(function (d) {
                  showMsg(
                    "signature-msg",
                    d.error || formUi.msg_signature_error || "",
                    true
                  );
                });
            }
          })
          .catch(function () {
            showMsg(
              "signature-msg",
              formUi.msg_connection_error || "",
              true
            );
            showConnectionError();
          });
      });
    }
  })();

  const submitBtn = document.getElementById("submit-form");
  if (submitBtn) {
    submitBtn.addEventListener("click", function () {
      performIntakeSubmit();
    });
  }

  const retryBtn = document.getElementById("tablet-form-retry-btn");
  if (retryBtn) {
    retryBtn.addEventListener("click", function () {
      hideConnectionError();
      retryBtn.blur();
    });
  }

  updateStepper(1);
  var hash = window.location.hash;
  var stepMatch = hash && hash.match(/^#step-([123])$/);
  if (stepMatch) {
    var step = parseInt(stepMatch[1], 10);
    if (step !== 1) goToStep(step);
  }
  updateLanguageLinksHash();
})();
