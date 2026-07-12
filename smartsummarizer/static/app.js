const form = document.getElementById("summarize-form");
const urlInput = document.getElementById("url-input");
const modelSelect = document.getElementById("model-select");
const submitBtn = document.getElementById("submit-btn");
const btnLabel = submitBtn.querySelector(".btn-label");
const btnSpinner = submitBtn.querySelector(".btn-spinner");
const formError = document.getElementById("form-error");
const resultPlaceholder = document.getElementById("result-placeholder");
const resultContent = document.getElementById("result-content");

function normalizeUrl(raw) {
  let url = raw.trim();
  if (!url) return url;
  if (!/^https?:\/\//i.test(url)) {
    url = `https://${url}`;
  }
  return url;
}

function showError(message) {
  formError.textContent = message;
  formError.classList.remove("hidden");
}

function hideError() {
  formError.classList.add("hidden");
  formError.textContent = "";
}

function setLoading(loading) {
  submitBtn.disabled = loading;
  btnLabel.textContent = loading ? "Summarizing…" : "Summarize";
  btnSpinner.classList.toggle("hidden", !loading);
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === "string"
      ? data.detail
      : JSON.stringify(data.detail || "Request failed");
    throw new Error(detail);
  }
  return data;
}

function renderResult(item) {
  resultPlaceholder.classList.add("hidden");
  resultContent.classList.remove("hidden");

  document.getElementById("result-source").className = `badge badge-source ${item.source_type}`;
  document.getElementById("result-source").textContent = item.source_type;
  document.getElementById("result-sentiment").className = `badge badge-sentiment ${item.sentiment}`;
  document.getElementById("result-sentiment").textContent = item.sentiment;
  document.getElementById("result-title").textContent = item.title;
  document.getElementById("result-url").href = item.url;
  document.getElementById("result-url").textContent = item.url;
  document.getElementById("result-words").textContent = item.word_count.toLocaleString();
  document.getElementById("result-model").textContent = item.model;
  document.getElementById("result-summary").textContent = item.summary;

  const pointsEl = document.getElementById("result-key-points");
  pointsEl.innerHTML = "";
  item.key_points.forEach((point) => {
    const li = document.createElement("li");
    li.textContent = point;
    pointsEl.appendChild(li);
  });
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  hideError();
  setLoading(true);

  try {
    const url = normalizeUrl(urlInput.value);
    const result = await api("/api/summarize", {
      method: "POST",
      body: JSON.stringify({ url, model: modelSelect.value }),
    });
    renderResult(result);
  } catch (err) {
    showError(err.message);
  } finally {
    setLoading(false);
  }
});
