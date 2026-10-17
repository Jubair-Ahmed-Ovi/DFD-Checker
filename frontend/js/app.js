const fileInput = document.getElementById('fileInput');
const chooseBtn = document.getElementById('chooseBtn');
const dropzone = document.getElementById('dropzone');
const fileInfo = document.getElementById('fileInfo');
const convertBtn = document.getElementById('convertBtn');
const statusBox = document.getElementById('status');
const result = document.getElementById('result');
const editor = document.getElementById('jsonEditor');
const validation = document.getElementById('validation');
const resultName = document.getElementById('resultName');

const auditBtn = document.getElementById('auditBtn');
const auditResult = document.getElementById('auditResult');

const copyBtn = document.getElementById('copyBtn');
const validateBtn = document.getElementById('validateBtn');
const downloadBtn = document.getElementById('downloadBtn');

let selected = null;

// --------------------------------------------------
// FILE UPLOAD
// --------------------------------------------------

chooseBtn.addEventListener('click', () => {
  fileInput.click();
});

fileInput.addEventListener('change', () => {
  setFile(fileInput.files[0]);
});

['dragenter', 'dragover'].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.add('drag');
  });
});

['dragleave', 'drop'].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.remove('drag');
  });
});

dropzone.addEventListener('drop', (event) => {
  setFile(event.dataTransfer.files[0]);
});

function setFile(file) {
  if (!file) return;

  selected = file;

  fileInfo.textContent =
    `Selected: ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`;

  convertBtn.disabled = false;
  statusBox.textContent = '';

  resetAuditReport();
}

// --------------------------------------------------
// API RESPONSE HELPERS
// --------------------------------------------------

async function readJsonResponse(response) {
  const text = await response.text();

  if (!text) return {};

  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

function getErrorMessage(
  data,
  fallback = 'The request failed.'
) {
  const detail = data && data.detail;

  if (typeof detail === 'string') {
    return detail;
  }

  if (detail !== undefined) {
    return JSON.stringify(detail);
  }

  if (data && typeof data.message === 'string') {
    return data.message;
  }

  return fallback;
}

function showJsonValidation(message, state) {
  validation.className =
    `validation ${state || ''}`.trim();

  validation.textContent = message;
}

// --------------------------------------------------
// RESET DFD AUDIT REPORT
// --------------------------------------------------

function resetAuditReport() {
  auditResult.className = 'audit-result hidden';
  auditResult.replaceChildren();
}

// --------------------------------------------------
// CONVERT IMAGE TO JSON
// --------------------------------------------------

convertBtn.addEventListener('click', async () => {
  if (!selected) return;

  convertBtn.disabled = true;
  statusBox.textContent = 'Converting image…';

  result.classList.add('hidden');
  resetAuditReport();
  showJsonValidation('', '');

  try {
    const formData = new FormData();
    formData.append('file', selected);

    const response = await fetch('/api/convert', {
      method: 'POST',
      body: formData
    });

    const data = await readJsonResponse(response);

    if (!response.ok) {
      throw new Error(
        getErrorMessage(data, 'Conversion failed.')
      );
    }

    if (
      !data.dfd_json ||
      typeof data.dfd_json !== 'object'
    ) {
      throw new Error(
        'The server response does not contain a valid dfd_json object.'
      );
    }

    editor.value = JSON.stringify(
      data.dfd_json,
      null,
      2
    );

    resultName.textContent =
      data.filename || selected.name;

    result.classList.remove('hidden');
    statusBox.textContent = 'Conversion complete.';

    result.scrollIntoView({
      behavior: 'smooth'
    });

  } catch (error) {
    statusBox.textContent =
      `Error: ${error.message}`;

  } finally {
    convertBtn.disabled = false;
  }
});

// --------------------------------------------------
// CLEAR OLD AUDIT WHEN JSON IS EDITED
// --------------------------------------------------

editor.addEventListener('input', () => {
  resetAuditReport();
});

// --------------------------------------------------
// COPY JSON
// --------------------------------------------------

copyBtn.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(editor.value);

    showJsonValidation(
      'JSON copied to clipboard.',
      'ok'
    );

  } catch (error) {
    showJsonValidation(
      `Could not copy JSON: ${error.message}`,
      'bad'
    );
  }
});

// --------------------------------------------------
// VALIDATE JSON STRUCTURE
// --------------------------------------------------

validateBtn.addEventListener('click', async () => {
  try {
    const obj = JSON.parse(editor.value);

    const response = await fetch('/api/validate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(obj)
    });

    const data = await readJsonResponse(response);

    if (!response.ok) {
      throw new Error(
        getErrorMessage(data, 'JSON validation failed.')
      );
    }

    const errors = Array.isArray(data.errors)
      ? data.errors
      : [];

    if (data.valid) {
      showJsonValidation(
        '✓ JSON structure is valid.',
        'ok'
      );

    } else {
      showJsonValidation(
        `✗ ${
          errors.length
            ? errors.join(' | ')
            : 'JSON validation failed.'
        }`,
        'bad'
      );
    }

  } catch (error) {
    const message =
      error instanceof SyntaxError
        ? `Invalid JSON syntax: ${error.message}`
        : error.message;

    showJsonValidation(
      `✗ ${message}`,
      'bad'
    );
  }
});

// --------------------------------------------------
// DISPLAY DFD AUDIT REPORT
// --------------------------------------------------

function renderAuditReport(data) {
  auditResult.replaceChildren();
  auditResult.classList.remove('hidden');

  const status = String(
    data.status || 'NEEDS_REVIEW'
  ).toUpperCase();

  const statusClass =
    status === 'VALID'
      ? 'valid'
      : status === 'INVALID'
        ? 'invalid'
        : 'review';

  const statusIcon =
    status === 'VALID'
      ? '✓'
      : status === 'INVALID'
        ? '✗'
        : '⚠';

  auditResult.className =
    `audit-result audit-${statusClass}`;

  // Report summary
  const summary = document.createElement('div');
  summary.className = 'audit-summary';

  summary.textContent =
    `${statusIcon} ${status.replace('_', ' ')} — ${
      data.summary || 'Audit completed.'
    }`;

  auditResult.appendChild(summary);

  // Error and warning counts
  const counts = document.createElement('p');
  counts.className = 'audit-counts';

  const checkedLevels =
    Array.isArray(data.checked_levels) &&
    data.checked_levels.length
      ? data.checked_levels.join(', ')
      : 'none';

  counts.textContent =
    `Levels checked: ${checkedLevels} | ` +
    `Errors: ${Number(data.error_count || 0)} | ` +
    `Warnings: ${Number(data.warning_count || 0)}`;

  auditResult.appendChild(counts);

  // List of rule violations
  const violations = Array.isArray(data.violations)
    ? data.violations
    : [];

  if (violations.length === 0) {
    const cleanMessage = document.createElement('p');

    cleanMessage.className = 'audit-clean';

    cleanMessage.textContent =
      'No structural DFD rule violations were detected. ' +
      'This does not guarantee that the diagram fully ' +
      'matches the real-world requirements.';

    auditResult.appendChild(cleanMessage);
    return;
  }

  const list = document.createElement('div');
  list.className = 'audit-violations';

  violations.forEach((violation) => {
    const card = document.createElement('article');

    const severity = String(
      violation.severity || 'warning'
    ).toLowerCase();

    card.className =
      `audit-violation severity-${severity}`;

    // Rule ID, severity, level and affected element
    const heading = document.createElement('h4');

    const details = [
      violation.rule_id || 'DFD RULE',
      severity.toUpperCase()
    ];

    if (
      violation.level !== null &&
      violation.level !== undefined
    ) {
      details.push(`Level ${violation.level}`);
    }

    if (violation.element_id) {
      details.push(String(violation.element_id));
    }

    heading.textContent = details.join(' · ');
    card.appendChild(heading);

    // Explanation
    const message = document.createElement('p');

    message.className = 'audit-message';

    message.textContent =
      violation.message || 'A rule needs review.';

    card.appendChild(message);

    // Suggested correction
    if (violation.suggestion) {
      const suggestion = document.createElement('p');

      suggestion.className = 'audit-suggestion';

      suggestion.textContent =
        `Suggested fix: ${violation.suggestion}`;

      card.appendChild(suggestion);
    }

    list.appendChild(card);
  });

  auditResult.appendChild(list);
}

// --------------------------------------------------
// CHECK DFD RULES
// --------------------------------------------------

auditBtn.addEventListener('click', async () => {
  let dfdJson;

  // Check JSON syntax before sending the request
  try {
    dfdJson = JSON.parse(editor.value);

  } catch (error) {
    auditResult.className =
      'audit-result audit-invalid';

    auditResult.replaceChildren();
    auditResult.classList.remove('hidden');

    const message = document.createElement('p');

    message.textContent =
      `Cannot check DFD rules because the JSON syntax is invalid: ${error.message}`;

    auditResult.appendChild(message);
    return;
  }

  auditBtn.disabled = true;

  const originalText = auditBtn.textContent;

  auditBtn.textContent = 'Checking rules…';

  auditResult.className = 'audit-result';
  auditResult.textContent = 'Checking DFD rules…';
  auditResult.classList.remove('hidden');

  try {
    const response = await fetch('/api/audit', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        dfd_json: dfdJson
      })
    });

    const data = await readJsonResponse(response);

    if (!response.ok) {
      throw new Error(
        getErrorMessage(data, 'DFD audit request failed.')
      );
    }

    renderAuditReport(data);

  } catch (error) {
    auditResult.className =
      'audit-result audit-invalid';

    auditResult.replaceChildren();
    auditResult.classList.remove('hidden');

    const message = document.createElement('p');

    message.textContent =
      `Could not check DFD rules: ${error.message}. ` +
      'Confirm that the /api/audit endpoint is implemented ' +
      'in the backend and the server has been restarted.';

    auditResult.appendChild(message);

  } finally {
    auditBtn.disabled = false;
    auditBtn.textContent = originalText;
  }
});

// --------------------------------------------------
// DOWNLOAD JSON
// --------------------------------------------------

downloadBtn.addEventListener('click', async () => {
  try {
    const obj = JSON.parse(editor.value);

    const response = await fetch('/api/download', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(obj)
    });

    if (!response.ok) {
      const data = await readJsonResponse(response);

      throw new Error(
        getErrorMessage(data, 'Download failed.')
      );
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);

    const link = document.createElement('a');

    link.href = url;
    link.download = 'dfd.json';

    document.body.appendChild(link);
    link.click();
    link.remove();

    window.setTimeout(() => {
      URL.revokeObjectURL(url);
    }, 1000);

  } catch (error) {
    showJsonValidation(
      `✗ ${error.message}`,
      'bad'
    );
  }
});