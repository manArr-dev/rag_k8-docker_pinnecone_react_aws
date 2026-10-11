import { type ChangeEvent, useState } from "react";
import { uploadDocument } from "../api";

interface UploadStatus {
  name: string;
  state: "uploading" | "done" | "error";
  detail?: string;
}

const KEY_STORAGE = "rag-admin-key";

function storedKey(): string {
  try {
    return sessionStorage.getItem(KEY_STORAGE) ?? "";
  } catch {
    return "";
  }
}

export function UploadPanel() {
  const [adminKey, setAdminKey] = useState(storedKey);
  const [uploads, setUploads] = useState<UploadStatus[]>([]);

  const saveKey = (value: string) => {
    setAdminKey(value);
    try {
      // Session-scoped: the key is gone when the tab closes.
      sessionStorage.setItem(KEY_STORAGE, value);
    } catch {
      // Storage unavailable (private mode); the key just isn't remembered.
    }
  };

  const onFiles = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    for (const file of files) {
      const update = (status: UploadStatus) =>
        setUploads((prev) => [status, ...prev.filter((u) => u.name !== file.name)]);
      update({ name: file.name, state: "uploading" });
      try {
        const result = await uploadDocument(file, adminKey);
        update({ name: file.name, state: "done", detail: `${result.chunks} chunks indexed` });
      } catch (err) {
        const detail = err instanceof Error ? err.message : "Upload failed";
        update({ name: file.name, state: "error", detail });
      }
    }
  };

  return (
    <section className="upload-panel" aria-label="Add documents">
      <label>
        Admin key
        <input
          type="password"
          value={adminKey}
          autoComplete="off"
          placeholder="X-API-Key for document uploads"
          onChange={(e) => saveKey(e.target.value)}
        />
      </label>
      <label>
        Files (PDF, TXT, MD)
        <input type="file" multiple accept=".pdf,.txt,.md" onChange={onFiles} />
      </label>
      {uploads.length > 0 && (
        <ul className="uploads">
          {uploads.map((u) => (
            <li key={u.name} className={u.state}>
              <span>{u.name}</span>
              <span>{u.state === "uploading" ? "Indexing…" : u.detail}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
