import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useLoad } from "../hooks";
import { Card, Field, Spinner, useToast } from "../ui";

export default function Patients() {
  const toast = useToast();
  const patients = useLoad(() => api.patients());
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.createPatient({ name, phone: phone || null, notes: notes || null });
      setName(""); setPhone(""); setNotes("");
      patients.reload();
      toast.show("Patient added", "ok");
    } catch (e2: any) {
      toast.show(e2?.message ?? "Failed", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Patients</h1>
      <div className="grid cols-2">
        <Card>
          <h2>All patients</h2>
          {patients.loading ? <Spinner /> : patients.data?.length ? (
            <table>
              <thead><tr><th>Name</th><th>Phone</th></tr></thead>
              <tbody>
                {patients.data.map((p) => (
                  <tr key={p.id}>
                    <td><Link to={`/patients/${p.id}`}>{p.name}</Link></td>
                    <td className="muted">{p.phone ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div className="list-empty">No patients yet.</div>}
        </Card>

        <Card>
          <h2>Add patient</h2>
          <form onSubmit={create}>
            <Field label="Name"><input value={name} onChange={(e) => setName(e.target.value)} required /></Field>
            <Field label="Phone"><input value={phone} onChange={(e) => setPhone(e.target.value)} /></Field>
            <Field label="Notes"><textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} /></Field>
            <button disabled={busy}>{busy ? "Saving…" : "Add patient"}</button>
          </form>
        </Card>
      </div>
    </>
  );
}
