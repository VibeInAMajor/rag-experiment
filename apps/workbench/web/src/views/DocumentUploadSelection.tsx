import type { LiveDocumentsModel } from "../hooks/useLiveDocuments";
import { DocumentUploadQueue } from "./DocumentUploadQueue";

export function DocumentUploadSelection({
  model,
  pdfAvailable,
  foldersPersisted,
  uploadAllowed,
}: {
  model: LiveDocumentsModel;
  pdfAvailable: boolean;
  foldersPersisted: boolean;
  uploadAllowed: boolean;
}) {
  const choose = (input: HTMLInputElement) => {
    model.chooseFiles(Array.from(input.files ?? []));
    input.value = "";
  };
  return (
    <>
      <label
        className="view-field documents-upload-field"
        htmlFor="document-files"
      >
        Choose files
        <input
          id="document-files"
          type="file"
          multiple
          accept={`.txt,.md,.markdown,.py${pdfAvailable ? ",.pdf" : ""}`}
          disabled={!uploadAllowed || model.uploadQueueBusy}
          onChange={(event) => choose(event.currentTarget)}
        />
      </label>
      <label
        className="view-field documents-upload-field"
        htmlFor="document-folder"
      >
        Choose folder (including subfolders)
        <input
          id="document-folder"
          type="file"
          multiple
          ref={(element) => {
            element?.setAttribute("webkitdirectory", "");
          }}
          disabled={!uploadAllowed || model.uploadQueueBusy}
          aria-describedby="upload-folder-help"
          onChange={(event) => choose(event.currentTarget)}
        />
      </label>
      <p id="upload-folder-help" className="detail-caption">
        All files in the selected folder and its subfolders are checked.
        Unsupported or oversized files appear as skipped. Empty folders contain
        no files to upload. Choosing again replaces the displayed queue and
        starts new operations.
      </p>
      {!foldersPersisted && (
        <p className="detail-notice">
          Folder uploads work in this session. Restart the updated local API to
          keep folder structure after a page refresh.
        </p>
      )}
      <DocumentUploadQueue model={model} uploadAllowed={uploadAllowed} />
    </>
  );
}
