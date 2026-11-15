import { useRef, useState } from "react";
import { API_BASE_URL } from "../config";

// Phone photos are 3-12 MB; the vision model doesn't need more than this, and it's faster on less.
const MAX_SIDE = 1024;

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Couldn't open that image. Try a JPEG or PNG photo."));
    };
    img.src = url;
  });
}

async function shrinkToJpeg(file) {
  const img = await loadImage(file);
  const scale = Math.min(1, MAX_SIDE / Math.max(img.naturalWidth, img.naturalHeight));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(img.naturalWidth * scale);
  canvas.height = Math.round(img.naturalHeight * scale);
  canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.85);
}

export default function PhotoIngredients({ onFound }) {
  const inputRef = useRef(null);
  const [result, setResult] = useState({ status: "idle" });
  const [preview, setPreview] = useState(null);
  const reading = result.status === "reading";

  const handleFile = async (file) => {
    if (!file) return;
    setResult({ status: "reading" });
    try {
      const image = await shrinkToJpeg(file);
      setPreview(image);
      const res = await fetch(`${API_BASE_URL}/ingredients/from-photo`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image }),
      });
      if (!res.ok) {
        throw new Error(
          res.status === 400
            ? "That file couldn't be read as a photo. Try a JPEG or PNG."
            : "Couldn't read the photo right now. Check that Ollama is running with llava, then try again."
        );
      }
      const { ingredients } = await res.json();
      onFound(ingredients);
      setResult({ status: "done", count: ingredients.length });
    } catch (err) {
      console.error(err);
      setResult({ status: "error", message: err.message });
    } finally {
      // Lets the same file be picked again after an error.
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <div className="photo-ingredients">
      <div className="photo-row">
        <button
          type="button"
          className="secondary-button"
          disabled={reading}
          onClick={() => inputRef.current?.click()}
        >
          {reading ? "Looking at your photo…" : "📷 Add from a photo"}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          hidden
          aria-label="Fridge or pantry photo"
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
        {preview && <img className="photo-preview" src={preview} alt="Your fridge or pantry photo" />}
      </div>
      <p className="photo-status" role="status">
        {reading && "Finding ingredients — this can take up to a minute."}
        {result.status === "done" &&
          (result.count > 0
            ? `Added ${result.count} ingredient${result.count === 1 ? "" : "s"} from your photo. Remove any it got wrong.`
            : "Didn't spot any ingredients in that photo. Try a closer, brighter shot.")}
      </p>
      {result.status === "error" && <p className="error-text">{result.message}</p>}
    </div>
  );
}
