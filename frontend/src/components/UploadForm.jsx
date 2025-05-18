import { useState } from 'react';
import axios from 'axios';

export default function UploadForm() {
  const [sourceType, setSourceType] = useState('zip');
  const [zipFile, setZipFile] = useState(null);
  const [repoUrl, setRepoUrl] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    const formData = new FormData();
    if (sourceType === 'zip') {
      formData.append('zip_file', zipFile);
    } else {
      formData.append('repo_url', repoUrl);
    }

    try {
      await axios.post('http://localhost:8000/upload', formData);
      alert('Submitted successfully!');
    } catch (error) {
      alert('Upload failed.');
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
          onChange={(e) => setZipFile(e.target.files[0])}
          className="mb-4"
        />
      ) : (
        <input
          type="text"
          placeholder="https://github.com/user/repo"
          value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
          className="border p-2 w-full mb-4"
        />
      )}
      <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded">
        Submit
      </button>
    </form>
  );
}
