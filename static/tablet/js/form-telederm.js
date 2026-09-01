/**
 * Tablet teledermatology intake – consents, adaptive questionnaire, signature, submit.
 */
(function () {
  "use strict";

  const config = window.__TABLET_TELEDERM_FORM_CONFIG__;
  if (!config) return;

  const formId = config.formId;
  const apiBase = config.apiBase || "/api/v1";
  const formLocale = config.formLocale || "de-DE";
  const schemaVersion = config.schemaVersion || 1;
  const anamnesisSchemaVersion = config.anamnesisSchemaVersion || 1;
  const hasAnamnesis = Boolean(config.hasAnamnesis);
  let signatureSaved = Boolean(config.hasSignature);
  let intakeSubmitInProgress = false;
  let autoSubmitAfterSignatureTimer = null;
  const AUTO_SUBMIT_AFTER_SIGNATURE_MS = 60 * 1000;

  const teledermInitialEl = document.getElementById("telederm-initial");
  const formUiEl = document.getElementById("form-ui");
  let teledermState = teledermInitialEl
    ? JSON.parse(teledermInitialEl.textContent || "{}")
    : {};
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

  function hideConnectionError() {
    const bar = document.getElementById("tablet-form-connection-error");
    if (bar) bar.style.display = "none";
  }

  function showConnectionError() {
    const bar = document.getElementById("tablet-form-connection-error");
    const textEl = bar && bar.querySelector(".tablet-form-connection-error-text");
    if (textEl) textEl.textContent = formUi.msg_connection_error || "";
    if (bar) bar.style.display = "flex";
  }

  const stepTitles = [
    formUi.step_1_title,
    formUi.step_2_title,
    formUi.step_3_title,
  ];

  function updateStepper(currentStep) {
    document.querySelectorAll(".tablet-form-stepper .stepper-dot").forEach(function (dot, i) {
      const step = i + 1;
      dot.classList.remove("current", "done");
      dot.setAttribute("aria-current", step === currentStep ? "step" : "false");
      if (step === currentStep) dot.classList.add("current");
      else if (step < currentStep) dot.classList.add("done");
    });
    document.querySelectorAll(".tablet-form-stepper .stepper-line").forEach(function (line, i) {
      line.classList.toggle("done", i + 1 < currentStep);
    });
  }

  function goToStep(stepNum) {
    document.querySelectorAll(".form-step").forEach(function (el) {
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
    if (stepNum === 3 && signatureSaved) scheduleAutoSubmitAfterSignature();
    else clearAutoSubmitAfterSignatureTimer();
  }

  function clearAutoSubmitAfterSignatureTimer() {
    if (autoSubmitAfterSignatureTimer) {
      clearTimeout(autoSubmitAfterSignatureTimer);
      autoSubmitAfterSignatureTimer = null;
    }
    const hint = document.getElementById("auto-submit-hint");
    if (hint) hint.style.display = "none";
  }

  function scheduleAutoSubmitAfterSignature() {
    clearAutoSubmitAfterSignatureTimer();
    const hint = document.getElementById("auto-submit-hint");
    if (hint && formUi.auto_submit_hint) {
      hint.textContent = formUi.auto_submit_hint;
      hint.style.display = "block";
    }
    autoSubmitAfterSignatureTimer = setTimeout(function () {
      submitIntakeForm();
    }, AUTO_SUBMIT_AFTER_SIGNATURE_MS);
  }

  function submitIntakeForm() {
    if (intakeSubmitInProgress || !signatureSaved) return;
    intakeSubmitInProgress = true;
    clearAutoSubmitAfterSignatureTimer();
    const btn = document.getElementById("submit-form");
    if (btn) btn.disabled = true;
    hideConnectionError();
    api("POST", "/intake-forms/" + formId + "/submit", {})
      .then(function (r) {
        if (r.ok) {
          window.location.href = "/tablet/form/" + formId + "/";
        } else {
          intakeSubmitInProgress = false;
          r.json()
            .catch(function () {
              return {};
            })
            .then(function (d) {
              showMsg("submit-msg", d.error || formUi.msg_submit_error || "", true);
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

  function renderTeledermQuestions() {
    const container = document.getElementById("telederm-questions");
    const triageEl = document.getElementById("telederm-triage-blocked");
    const summarySection = document.getElementById("telederm-summary-preview");
    const summaryContent = document.getElementById("telederm-summary-content");
    if (!container) return;

    container.innerHTML = "";
    const blocked = Boolean(teledermState.triage_blocked);
    if (triageEl) {
      triageEl.textContent = blocked
        ? formUi.telederm_triage_blocked || ""
        : "";
      triageEl.style.display = blocked ? "block" : "none";
    }

    (teledermState.questions || []).forEach(function (q) {
      const block = document.createElement("div");
      block.className = "field telederm-field";
      block.dataset.questionId = q.question_id;
      block.dataset.required = q.is_required ? "true" : "false";
      block.dataset.answerType = q.answer_type;

      const title = document.createElement("strong");
      title.textContent =
        (q.question_text || q.question_id) + (q.is_required ? " *" : "");
      block.appendChild(title);

      const msg = document.createElement("div");
      msg.className = "telederm-field-msg error";
      msg.style.display = "none";
      block.appendChild(msg);

      const answer = q.answer || {};
      const selected = answer.selected || [];
      const inputName = "td-" + q.question_id;

      if (q.answer_type === "SINGLE") {
        (q.options || []).forEach(function (opt) {
          const label = document.createElement("label");
          const input = document.createElement("input");
          input.type = "radio";
          input.name = inputName;
          input.value = opt.code;
          if (selected.indexOf(opt.code) >= 0) input.checked = true;
          label.appendChild(input);
          label.appendChild(document.createTextNode(" " + (opt.label || opt.code)));
          block.appendChild(label);
        });
      } else if (q.answer_type === "MULTIPLE") {
        (q.options || []).forEach(function (opt) {
          const label = document.createElement("label");
          const input = document.createElement("input");
          input.type = "checkbox";
          input.name = inputName;
          input.value = opt.code;
          if (selected.indexOf(opt.code) >= 0) input.checked = true;
          label.appendChild(input);
          label.appendChild(document.createTextNode(" " + (opt.label || opt.code)));
          block.appendChild(label);
        });
      } else if (q.answer_type === "FREE_TEXT") {
        const textInput = document.createElement("input");
        textInput.type = "text";
        textInput.name = inputName + "-text";
        textInput.value = answer.free_text || "";
        textInput.placeholder = formUi.notes_placeholder || "";
        block.appendChild(textInput);
      }

      container.appendChild(block);
    });

    const preview = teledermState.clinical_summary_preview;
    if (summarySection && summaryContent && preview && !blocked) {
      let html = "";
      if (preview.problem_label) {
        html +=
          "<p><strong>" +
          (formUi.telederm_problem_label || "") +
          "</strong> " +
          preview.problem_label +
          "</p>";
      }
      (preview.lines || []).forEach(function (line) {
        html +=
          "<p class=\"small mb-1\"><strong>" +
          (line.label || "") +
          "</strong><br/><span class=\"text-muted\">" +
          (line.value || "—") +
          "</span></p>";
      });
      summaryContent.innerHTML = html;
      summarySection.style.display = html ? "block" : "none";
    } else if (summarySection) {
      summarySection.style.display = "none";
    }
  }

  function collectTeledermAnswers() {
    const answers = {};
    document.querySelectorAll("#telederm-questions .telederm-field").forEach(function (block) {
      const qid = block.dataset.questionId;
      const answerType = block.dataset.answerType;
      const inputName = "td-" + qid;
      if (answerType === "FREE_TEXT") {
        const textInput = block.querySelector('input[name="' + inputName + '-text"]');
        answers[qid] = {
          selected: [],
          free_text: textInput ? textInput.value.trim() : null,
        };
        return;
      }
      const selected = [];
      block.querySelectorAll('input[name="' + inputName + '"]:checked').forEach(function (el) {
        selected.push(el.value);
      });
      answers[qid] = { selected: selected, free_text: null };
    });
    return answers;
  }

  function saveTeledermPayload() {
    const localeQuery = "?form_locale=" + encodeURIComponent(formLocale);
    return api("PUT", "/intake-forms/" + formId + "/telederm-payload" + localeQuery, {
      schema_version: schemaVersion,
      answers: collectTeledermAnswers(),
      chief_complaint_path: teledermState.chief_complaint_path || null,
    }).then(function (r) {
      if (!r.ok) {
        return r
          .json()
          .catch(function () {
            return {};
          })
          .then(function (d) {
            throw new Error(d.error || formUi.msg_save_error || "Save failed");
          });
      }
      return r.json().then(function (ctx) {
        if (ctx.telederm) teledermState = ctx.telederm;
        renderTeledermQuestions();
        return ctx;
      });
    });
  }

  function collectAnamnesisAnswers() {
    const answers = [];
    document.querySelectorAll("#anamnesis-section [data-question-code]").forEach(function (block) {
      const code = block.dataset.questionCode;
      const selected_option_codes = [];
      block.querySelectorAll('input[type="radio"]:checked, input[type="checkbox"]:checked').forEach(function (el) {
        selected_option_codes.push(el.value);
      });
      const textInput = block.querySelector('input[type="text"]');
      answers.push({
        question_code: code,
        selected_option_codes: selected_option_codes,
        free_text: textInput && textInput.value.trim() ? textInput.value.trim() : null,
      });
    });
    return answers;
  }

  function saveAnamnesisIfPresent() {
    if (!hasAnamnesis) return Promise.resolve();
    return api("PUT", "/intake-forms/" + formId + "/anamnesis", {
      anamnesis_schema_version: anamnesisSchemaVersion,
      answers: collectAnamnesisAnswers(),
    }).then(function (r) {
      if (!r.ok) {
        return r
          .json()
          .catch(function () {
            return {};
          })
          .then(function (d) {
            throw new Error(d.error || formUi.msg_save_error || "Save failed");
          });
      }
    });
  }

  function clearConsentBlockMsgs() {
    document.querySelectorAll("#consents-section .consent-block-msg").forEach(function (el) {
      el.textContent = "";
      el.style.display = "none";
    });
  }

  function showConsentBlockMsg(block, text, isError) {
    const msgEl = block && block.querySelector(".consent-block-msg");
    if (!msgEl) return;
    msgEl.textContent = text || "";
    msgEl.className = "consent-block-msg " + (isError === false ? "success" : "error");
    msgEl.style.display = text ? "block" : "none";
  }

  function findFirstInvalidRequiredConsentBlock(consentBlocks) {
    var i;
    for (i = 0; i < consentBlocks.length; i++) {
      const block = consentBlocks[i];
      if (block.dataset.required !== "true") continue;
      const multi = block.querySelectorAll('input[name="multi-consent"]');
      if (multi.length) {
        if (!block.querySelector('input[name="multi-consent"]:checked')) return block;
      } else {
        const cb = block.querySelector('input[name="consent"]');
        if (!cb || !cb.checked) return block;
      }
    }
    return null;
  }

  renderTeledermQuestions();

  const teledermSection = document.getElementById("telederm-section");
  if (teledermSection) {
    teledermSection.addEventListener("change", function () {
      saveTeledermPayload().catch(function (err) {
        showMsg("telederm-msg", err.message || formUi.msg_save_error || "", true);
      });
    });
    teledermSection.addEventListener(
      "input",
      debounce(function () {
        saveTeledermPayload().catch(function () {});
      }, 400)
    );
  }

  function debounce(fn, ms) {
    var timer;
    return function () {
      clearTimeout(timer);
      timer = setTimeout(fn, ms);
    };
  }

  const btnStep1Next = document.getElementById("btn-step1-next");
  if (btnStep1Next) {
    btnStep1Next.addEventListener("click", function () {
      const consentBlocks = document.querySelectorAll("#consents-section .consent-block");
      const firstInvalid = findFirstInvalidRequiredConsentBlock(consentBlocks);
      if (firstInvalid) {
        showConsentBlockMsg(
          firstInvalid,
          formUi.validation_consents_required || "",
          true
        );
        return;
      }
      clearConsentBlockMsgs();
      hideConnectionError();
      const consents = [];
      consentBlocks.forEach(function (block) {
        const consentId = block.dataset.consentId;
        const multiCheckboxes = block.querySelectorAll('input[name="multi-consent"]');
        if (multiCheckboxes.length) {
          const selectedCodes = [];
          block.querySelectorAll('input[name="multi-consent"]:checked').forEach(function (el) {
            selectedCodes.push(el.value);
          });
          consents.push({
            consent_definition_id: consentId,
            accepted: selectedCodes.length > 0,
            selected_option_codes: selectedCodes,
          });
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
          if (r.ok) goToStep(2);
          else {
            r.json().catch(function () {
              return {};
            }).then(function (d) {
              showConsentBlockMsg(
                consentBlocks[0],
                d.error || formUi.msg_save_error || "",
                true
              );
            });
          }
        })
        .catch(function () {
          showConnectionError();
        });
    });
  }

  const btnStep2Back = document.getElementById("btn-step2-back");
  if (btnStep2Back) btnStep2Back.addEventListener("click", function () {
    goToStep(1);
  });
  const btnStep3Back = document.getElementById("btn-step3-back");
  if (btnStep3Back) btnStep3Back.addEventListener("click", function () {
    goToStep(2);
  });

  const btnStep2Next = document.getElementById("btn-step2-next");
  if (btnStep2Next) {
    btnStep2Next.addEventListener("click", function () {
      hideConnectionError();
      showMsg("telederm-msg", "", false);
      saveTeledermPayload()
        .then(function () {
          if (teledermState.triage_blocked) {
            showMsg(
              "telederm-msg",
              formUi.telederm_triage_blocked || "",
              true
            );
            return;
          }
          return saveAnamnesisIfPresent();
        })
        .then(function () {
          if (teledermState.triage_blocked) return;
          goToStep(3);
        })
        .catch(function (err) {
          showMsg("telederm-msg", err.message || formUi.msg_connection_error || "", true);
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

    function getPos(e) {
      const rect = canvas.getBoundingClientRect();
      const x = e.clientX != null ? e.clientX : e.touches && e.touches[0] ? e.touches[0].clientX : 0;
      const y = e.clientY != null ? e.clientY : e.touches && e.touches[0] ? e.touches[0].clientY : 0;
      const scaleX = rect.width > 0 ? canvas.width / rect.width : 1;
      const scaleY = rect.height > 0 ? canvas.height / rect.height : 1;
      return {
        x: (x - rect.left) * scaleX,
        y: (y - rect.top) * scaleY,
      };
    }

    canvas.addEventListener("pointerdown", function (e) {
      e.preventDefault();
      drawing = true;
      canvas.setPointerCapture(e.pointerId);
      const p = getPos(e);
      ctx.beginPath();
      ctx.moveTo(p.x, p.y);
    });
    canvas.addEventListener("pointermove", function (e) {
      if (!drawing) return;
      e.preventDefault();
      const p = getPos(e);
      ctx.lineTo(p.x, p.y);
      ctx.stroke();
      hasDrawn = true;
    });
    canvas.addEventListener("pointerup", function (e) {
      e.preventDefault();
      drawing = false;
    });

    const clearBtn = document.getElementById("clear-signature");
    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        hasDrawn = false;
        signatureSaved = false;
        const submitBtn = document.getElementById("submit-form");
        if (submitBtn) submitBtn.disabled = true;
        clearAutoSubmitAfterSignatureTimer();
      });
    }

    const saveSigBtn = document.getElementById("save-signature");
    if (saveSigBtn) {
      saveSigBtn.addEventListener("click", function () {
        if (!hasDrawn && !signatureSaved) {
          showMsg("signature-msg", formUi.validation_signature_required || "", true);
          return;
        }
        const dataUrl = canvas.toDataURL("image/png");
        api("POST", "/intake-forms/" + formId + "/signature", {
          signature_base64: dataUrl,
        })
          .then(function (r) {
            if (r.ok) {
              signatureSaved = true;
              showMsg("signature-msg", "", false);
              const savedEl = document.getElementById("signature-saved");
              if (savedEl) savedEl.style.display = "inline";
              const submitBtn = document.getElementById("submit-form");
              if (submitBtn) submitBtn.disabled = false;
              scheduleAutoSubmitAfterSignature();
            } else {
              r.json().catch(function () {
                return {};
              }).then(function (d) {
                showMsg("signature-msg", d.error || formUi.msg_save_error || "", true);
              });
            }
          })
          .catch(function () {
            showMsg("signature-msg", formUi.msg_connection_error || "", true);
            showConnectionError();
          });
      });
    }
  })();

  const submitBtn = document.getElementById("submit-form");
  if (submitBtn) {
    submitBtn.addEventListener("click", submitIntakeForm);
  }

  const retryBtn = document.getElementById("tablet-form-retry-btn");
  if (retryBtn) {
    retryBtn.addEventListener("click", function () {
      hideConnectionError();
    });
  }
})();
