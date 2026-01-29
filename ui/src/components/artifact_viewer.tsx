// Author: Bradley R. Kinnard
import type { Artifact } from '../api/types'

interface ArtifactViewerProps {
  artifact: Artifact
}

export function ArtifactViewer({ artifact }: ArtifactViewerProps) {
  return (
    <div className="card">
      <h3>Artifact: {artifact.id}</h3>
      <table className="table">
        <tbody>
          <tr>
            <th>Content Hash</th>
            <td className="hash evidence-link">{artifact.content_hash}</td>
          </tr>
          <tr>
            <th>Type</th>
            <td>{artifact.artifact_type}</td>
          </tr>
          <tr>
            <th>Size</th>
            <td>{artifact.size_bytes.toLocaleString()} bytes</td>
          </tr>
          <tr>
            <th>Created By</th>
            <td>{artifact.created_by}</td>
          </tr>
          {artifact.run_id && (
            <tr>
              <th>Run</th>
              <td className="hash">{artifact.run_id}</td>
            </tr>
          )}
          {artifact.filename && (
            <tr>
              <th>Filename</th>
              <td>{artifact.filename}</td>
            </tr>
          )}
          <tr>
            <th>Created</th>
            <td>{new Date(artifact.created_at).toLocaleString()}</td>
          </tr>
        </tbody>
      </table>
      <div style={{ marginTop: '1rem' }}>
        <a
          href={`/api/v1/artifacts/${artifact.id}`}
          className="btn btn-primary"
          target="_blank"
          rel="noopener noreferrer"
        >
          Download
        </a>
      </div>
    </div>
  )
}
