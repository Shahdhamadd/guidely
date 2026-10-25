const API_URL = "http://localhost:8000";

export const QUERY_LOG_CSV_URL = API_URL + "/logs/queries.csv";

export async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(API_URL + path, options);
  } catch {
    throw new Error("Cannot reach the Guidely server. Is the backend running?");
  }

  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error("The server sent an answer Guidely could not read. Please try again.");
  }
  if (!response.ok) {
    throw new Error(data.error || "Something went wrong.");
  }
  return data;
}

export async function askQuestionStream(question, category, history = [], onText) {
  let response;
  try {
    response = await fetch(API_URL + "/search/ask/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, category, history }),
    });
  } catch {
    throw new Error("Cannot reach the Guidely server. Is the backend running?");
  }

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || "Something went wrong.");
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  let answer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;

    const lines = buffer.split("\n");
    buffer = lines.pop();
    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line);
      if (event.type === "token") {
        answer += event.text;
        onText(answer);
      } else if (event.type === "error") {
        throw new Error(event.error);
      } else if (event.type === "done") {
        return event;
      }
    }
  }
  throw new Error("The answer was cut off. Please try again.");
}

export function getDocuments() {
  return request("/documents");
}

export function getDocument(name) {
  return request(`/documents/${encodeURIComponent(name)}`);
}

export function saveDocument(name, text) {
  return request(`/documents/${encodeURIComponent(name)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

export function deleteDocument(name) {
  return request(`/documents/${encodeURIComponent(name)}`, { method: "DELETE" });
}

export function setDocumentCategory(name, category) {
  return request(`/documents/${encodeURIComponent(name)}/category`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ category }),
  });
}

export function uploadDocument(file, category) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("category", category);
  return request("/documents/upload", { method: "POST", body: formData });
}

export function reindexDocuments() {
  return request("/documents/index", { method: "POST" });
}
