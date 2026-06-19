import { api } from "../api";
import { useLoad } from "../hooks";
import { Card, Spinner } from "../ui";

export default function Audit() {
  const logs = useLoad(() => api.auditLogs());
  return (
    <>
      <h1>Audit trail</h1>
      <p className="muted" style={{ marginTop: -4 }}>Who changed what and when — complete from the first entry.</p>
      <Card>
        {logs.loading ? <Spinner /> : logs.data?.length ? (
          <table>
            <thead><tr><th>When</th><th>Action</th><th>Entity</th><th>ID</th><th>User</th></tr></thead>
            <tbody>
              {logs.data.map((l) => (
                <tr key={l.id}>
                  <td className="muted">{new Date(l.at).toLocaleString()}</td>
                  <td>{l.action}</td>
                  <td>{l.entity_type}</td>
                  <td className="muted">{l.entity_id ?? "—"}</td>
                  <td className="muted">{l.user_id ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="list-empty">No activity yet.</div>}
      </Card>
    </>
  );
}
