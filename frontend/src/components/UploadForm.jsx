import { useState } from 'react';
import axios from 'axios';

export default function UploadForm({ onAppReady }) {
  const [sourceType, setSourceType] = useState('zip');
  const [zipFile, setZipFile] = useState(null);
  const [repoUrl, setRepoUrl] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      let res;
      if (sourceType === 'zip') {
        // ──────────── ZIP UPLOAD ────────────
        const formData = new FormData();
        formData.append('file', zipFile);
        res = await axios.post(
          'http://localhost:8000/upload',
          formData,
          { headers: { 'Content-Type': 'multipart/form-data' } }
        );
      } else {
        // ──────────── GITHUB CLONE ────────────
        res = await axios.post(
          'http://localhost:8000/clone',
          { repo_url: repoUrl },            // <-- must be "repo_url"
          { headers: { 'Content-Type': 'application/json' } }
        );
      }

      const { app_id } = res.data;
      // Notify parent (or next step) that we have an app_id
      onAppReady(app_id);
    } catch (err) {
      console.error(err);
      alert('Failed to upload/clone. Check console for details.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="bg-white p-4 rounded shadow mb-6">
      <div className="mb-4">
        <label className="mr-4">
          <input
            type="radio"
            name="sourceType"
            value="zip"
            checked={sourceType === 'zip'}
            onChange={() => setSourceType('zip')}
          />{' '}
          Upload ZIP
        </label>
        <label>
          <input
            type="radio"
            name="sourceType"
            value="github"
            checked={sourceType === 'github'}
            onChange={() => setSourceType('github')}
          />{' '}
          GitHub Repo
        </label>
      </div>

      {sourceType === 'zip' ? (
        <input
          type="file"
          accept=".zip"
          required
          onChange={(e) => setZipFile(e.target.files[0])}
          className="mb-4"
        />
      ) : (
        <input
          type="url"
          placeholder="https://github.com/user/repo.git"
          value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
          required
          className="border p-2 w-full mb-4"
        />
      )}

      <button
        type="submit"
        className="bg-blue-600 text-white px-4 py-2 rounded"
        disabled={loading}
      >
        {loading ? 'Processing...' : 'Submit'}
      </button>
    </form>
  );
}
