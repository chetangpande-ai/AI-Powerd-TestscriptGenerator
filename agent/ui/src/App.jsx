import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertCircle,
  Check,
  Clock,
  Code2,
  GitBranch,
  GitPullRequest,
  Loader2,
  Play,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import "./styles.css";

const API_BASE = "http://127.0.0.1:8000/api";

const emptyForm = {
  repository_url: "",
  branch: "main",
  scenario: "",
  guidelines: "",
  force_generate: false,
};

function App() {
  const [form, setForm] = useState(emptyForm);
  const [run, setRun] = useState(null);
  const [activeStageId, setActiveStageId] = useState("request");
  const [activeFile, setActiveFile] = useState(0);
  const [busy, setBusy] = useState(false);
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState("");
  const [reviewerNote, setReviewerNote] = useState("");
  const [runValidation, setRunValidation] = useState(true);

  useEffect(() => {
    const runId = new URLSearchParams(window.location.search).get("run");
    if (!runId) return;
    let cancelled = false;
    async function loadRun() {
      setBusy(true);
      setError("");
      try {
        const response = await fetch(`${API_BASE}/runs/${runId}`);
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail ?? "Unable to load workflow.");
        if (!cancelled) {
          setRun(payload);
          setActiveStageId(firstInterestingStage(payload));
        }
      } catch (caught) {
        if (!cancelled) setError(caught.message);
      } finally {
        if (!cancelled) setBusy(false);
      }
    }
    loadRun();
    return () => {
      cancelled = true;
    };
  }, []);

  const activeStage = useMemo(() => {
    const stages = run?.stages ?? [];
    return stages.find((stage) => stage.id === activeStageId) ?? stages[0] ?? null;
  }, [run, activeStageId]);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setRun(null);
    setActiveFile(0);
    try {
      const response = await fetch(`${API_BASE}/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const payload = await response.json();
      const nextRun = response.ok ? payload : payload.detail ?? payload;
      setRun(nextRun);
      setActiveStageId(firstInterestingStage(nextRun));
      if (!response.ok) {
        throw new Error(nextRun?.result?.summary ?? "Generation workflow failed.");
      }
    } catch (caught) {
      setError(caught.message);
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (!run?.id) return;
    setApproving(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/runs/${run.id}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reviewer_note: reviewerNote,
          run_validation: runValidation,
        }),
      });
      const payload = await response.json();
      const nextRun = response.ok ? payload : payload.detail ?? payload;
      setRun(nextRun);
      setActiveStageId(firstInterestingStage(nextRun));
      if (!response.ok) {
        throw new Error(nextRun?.result?.summary ?? "Approval workflow failed.");
      }
    } catch (caught) {
      setError(caught.message);
    } finally {
      setApproving(false);
    }
  }

  async function refreshRun() {
    if (!run?.id) return;
    setError("");
    try {
      const response = await fetch(`${API_BASE}/runs/${run.id}`);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Unable to refresh workflow.");
      setRun(payload);
      setActiveStageId(firstInterestingStage(payload));
    } catch (caught) {
      setError(caught.message);
    }
  }

  function updateField(name, value) {
    setForm((current) => ({ ...current, [name]: value }));
  }

  return (
    <main className="app-shell">
      <header className="app-header">
        <div className="brand-mark">
          <Sparkles size={22} />
        </div>
        <div>
          <p className="eyebrow">Repository-aware automation agent</p>
          <h1>Test Script Generator Workflow</h1>
        </div>
      </header>

      <section className="start-panel">
        <form onSubmit={submit} className="start-form">
          <label>
            <span>GitHub Repository URL</span>
            <input
              value={form.repository_url}
              onChange={(event) => updateField("repository_url", event.target.value)}
              placeholder="https://github.com/org/automation-repo.git"
              required
            />
          </label>
          <label>
            <span>Branch</span>
            <input
              value={form.branch}
              onChange={(event) => updateField("branch", event.target.value)}
              placeholder="main"
              required
            />
          </label>
          <label className="scenario-field">
            <span>Scenario</span>
            <textarea
              value={form.scenario}
              onChange={(event) => updateField("scenario", event.target.value)}
              placeholder="Describe the test automation scenario."
              required
            />
          </label>
          <label className="guidelines-field">
            <span>Guidelines</span>
            <textarea
              value={form.guidelines}
              onChange={(event) => updateField("guidelines", event.target.value)}
              placeholder="Optional project rules, naming conventions, and assertions."
            />
          </label>
          <label className="toggle-row">
            <input
              type="checkbox"
              checked={form.force_generate}
              onChange={(event) => updateField("force_generate", event.target.checked)}
            />
            <span>Force generation</span>
          </label>
          <button className="primary-action" type="submit" disabled={busy}>
            {busy ? <Loader2 className="spin" size={18} /> : <Play size={18} />}
            <span>{busy ? "Running" : "Start workflow"}</span>
          </button>
        </form>
      </section>

      {error && (
        <div className="notice error">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      <section className="workflow-shell">
        <WorkflowOnly
          run={run}
          busy={busy}
          activeStageId={activeStageId}
          setActiveStageId={setActiveStageId}
          refreshRun={refreshRun}
        />
        <StageDetails
          run={run}
          activeStage={activeStage}
          activeFile={activeFile}
          setActiveFile={setActiveFile}
          reviewerNote={reviewerNote}
          setReviewerNote={setReviewerNote}
          runValidation={runValidation}
          setRunValidation={setRunValidation}
          approve={approve}
          approving={approving}
        />
      </section>
    </main>
  );
}

function WorkflowOnly({ run, busy, activeStageId, setActiveStageId, refreshRun }) {
  const stages = run?.stages ?? defaultStages(busy);
  return (
    <section className="workflow-panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Workflow</p>
          <h2>{run ? run.status.replaceAll("_", " ") : "Ready"}</h2>
        </div>
        {run?.working_branch && (
          <div className="workflow-actions">
            <button className="icon-action" type="button" onClick={refreshRun} aria-label="Refresh workflow">
              <RefreshCw size={15} />
            </button>
            <div className="branch-chip">
              <GitBranch size={15} />
              <span>{run.working_branch}</span>
            </div>
          </div>
        )}
      </div>

      <div className="stage-list">
        {stages.map((stage, index) => (
          <button
            className={`stage-card ${stage.status} ${activeStageId === stage.id ? "active" : ""}`}
            key={stage.id}
            type="button"
            onClick={() => setActiveStageId(stage.id)}
          >
            <span className="stage-number">{String(index + 1).padStart(2, "0")}</span>
            <StageIcon status={stage.status} />
            <span className="stage-text">
              <strong>{stage.label}</strong>
              <small>{stage.detail || stage.status}</small>
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

function StageDetails({
  run,
  activeStage,
  activeFile,
  setActiveFile,
  reviewerNote,
  setReviewerNote,
  runValidation,
  setRunValidation,
  approve,
  approving,
}) {
  if (!run) {
    return (
      <section className="detail-panel empty-detail">
        <Clock size={32} />
        <h2>Start a workflow to see stage details.</h2>
        <p>Each workflow stage opens here with the exact reuse analysis, generated files, review controls, and PR status.</p>
      </section>
    );
  }

  return (
    <section className="detail-panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Stage details</p>
          <h2>{activeStage?.label ?? "Workflow"}</h2>
        </div>
        <StatusPill status={activeStage?.status} />
      </div>
      <p className="stage-detail">{activeStage?.detail || "No additional details for this stage yet."}</p>
      <StageSpecificContent
        run={run}
        stageId={activeStage?.id}
        activeFile={activeFile}
        setActiveFile={setActiveFile}
        reviewerNote={reviewerNote}
        setReviewerNote={setReviewerNote}
        runValidation={runValidation}
        setRunValidation={setRunValidation}
        approve={approve}
        approving={approving}
      />
    </section>
  );
}

function StageSpecificContent(props) {
  const { run, stageId } = props;
  if (stageId === "analyze") return <ReuseDetails run={run} />;
  if (stageId === "crawl") return <WebDiscoveryDetails run={run} />;
  if (stageId === "generate") return <GeneratedDetails {...props} />;
  if (stageId === "review" || stageId === "approve") return <ReviewAndApproveDetails {...props} />;
  if (stageId === "validate") return <ValidationDetails run={run} />;
  if (stageId === "commit" || stageId === "push" || stageId === "pr") return <PrDetails run={run} />;
  return <BasicRunDetails run={run} />;
}

function BasicRunDetails({ run }) {
  return (
    <div className="detail-stack">
      <InfoRow label="Repository" value={run.repository_url} />
      <InfoRow label="Base branch" value={run.base_branch} />
      <InfoRow label="Decision" value={run.result?.decision} />
      <InfoRow label="Summary" value={run.result?.summary} />
    </div>
  );
}

function ReuseDetails({ run }) {
  const analysis = run.reusability_analysis ?? {};
  const reusedFiles = analysis.reused_files ?? [];
  return (
    <div className="detail-stack">
      <InfoRow label="Decision" value={run.result?.decision} />
      <InfoRow label="Summary" value={analysis.summary ?? run.result?.summary} />
      {analysis.existing_match && <InfoRow label="Existing match" value={analysis.existing_match} />}
      <div className="file-list">
        <span>Reusable context</span>
        {reusedFiles.length === 0 && <p>No reusable context selected.</p>}
        {reusedFiles.map((file) => <code key={file}>{file}</code>)}
      </div>
    </div>
  );
}

function WebDiscoveryDetails({ run }) {
  const discovery = run.web_discovery ?? {};
  const pages = discovery.pages ?? [];
  const rawSteps = discovery.raw_script ?? [];
  if (!discovery.enabled) {
    return (
      <div className="notice muted-notice">
        <Clock size={18} />
        <span>{discovery.summary || "Web crawl was skipped because this scenario was not detected as a web UI flow."}</span>
      </div>
    );
  }

  return (
    <div className="detail-stack">
      <InfoRow label="Summary" value={discovery.summary} />
      <div className="file-list">
        <span>Target URLs</span>
        {(discovery.urls ?? []).map((url) => <code key={url}>{url}</code>)}
      </div>
      <div className="file-list">
        <span>Raw action plan</span>
        {rawSteps.map((step, index) => <code key={`${step}-${index}`}>{`${index + 1}. ${step}`}</code>)}
      </div>
      <div className="evidence-grid">
        {pages.length === 0 && <p className="muted">No page evidence was collected.</p>}
        {pages.map((page) => (
          <article className="evidence-panel" key={page.url}>
            <h3>{page.title || "Untitled page"}</h3>
            <code>{page.final_url || page.url}</code>
            {page.error ? <p className="error-text">{page.error}</p> : <PageEvidence page={page} />}
          </article>
        ))}
      </div>
    </div>
  );
}

function PageEvidence({ page }) {
  const groups = [
    ["Inputs", page.inputs ?? []],
    ["Buttons", page.buttons ?? []],
    ["Forms", page.forms ?? []],
    ["Links", page.links ?? []],
  ];
  return (
    <div className="evidence-sections">
      {groups.map(([label, items]) => (
        <div className="file-list" key={label}>
          <span>{label}</span>
          {items.length === 0 && <p className="muted">None detected.</p>}
          {items.slice(0, 8).map((item, index) => (
            <code key={`${label}-${index}`}>{formatEvidence(item)}</code>
          ))}
        </div>
      ))}
    </div>
  );
}

function formatEvidence(item) {
  return Object.entries(item)
    .filter(([, value]) => value)
    .map(([key, value]) => `${key}: ${value}`)
    .join(" | ");
}

function GeneratedDetails({ run, activeFile, setActiveFile }) {
  const files = run.result?.files ?? [];
  if (run.result?.decision === "reuse_existing") {
    return (
      <div className="notice success">
        <Check size={18} />
        <span>{run.result.summary}</span>
      </div>
    );
  }
  if (files.length === 0) {
    return <p className="muted">No generated files are available for this run.</p>;
  }
  const selectedFile = files[activeFile] ?? files[0];
  return <FileReview files={files} selectedFile={selectedFile} activeFile={activeFile} setActiveFile={setActiveFile} />;
}

function ReviewAndApproveDetails(props) {
  const { run, reviewerNote, setReviewerNote, runValidation, setRunValidation, approve, approving } = props;
  const files = run.result?.files ?? [];
  const canApprove = run.result?.decision === "generate" && files.length > 0 && run.status !== "pull_request_created";
  const disabledReason = getApprovalDisabledReason(run, files);
  if (run.pull_request?.html_url) {
    return (
      <a className="pr-link" href={run.pull_request.html_url} target="_blank" rel="noreferrer">
        Open PR #{run.pull_request.number}
      </a>
    );
  }
  return (
    <div className="detail-stack">
      {!canApprove && disabledReason && (
        <div className="notice muted-notice">
          <AlertCircle size={18} />
          <span>{disabledReason}</span>
        </div>
      )}
      <GeneratedDetails {...props} />
      <label>
        <span>Reviewer note</span>
        <textarea
          value={reviewerNote}
          onChange={(event) => setReviewerNote(event.target.value)}
          placeholder="Optional note for the commit message."
        />
      </label>
      <label className="toggle-row">
        <input
          type="checkbox"
          checked={runValidation}
          onChange={(event) => setRunValidation(event.target.checked)}
        />
        <span>Run Maven validation before PR</span>
      </label>
      <button className="primary-action approve-action" disabled={!canApprove || approving} onClick={approve}>
        {approving ? <Loader2 className="spin" size={18} /> : <GitPullRequest size={18} />}
        <span>{approving ? "Creating PR" : "Approve and raise PR"}</span>
      </button>
    </div>
  );
}

function ValidationDetails({ run }) {
  return (
    <div className="detail-stack">
      <div className="file-list">
        <span>Validation commands</span>
        {(run.result?.validation_commands ?? []).map((command) => <code key={command}>{command}</code>)}
      </div>
      {run.validation_output && <pre className="code-view"><code>{run.validation_output}</code></pre>}
    </div>
  );
}

function PrDetails({ run }) {
  return (
    <div className="detail-stack">
      <InfoRow label="Working branch" value={run.working_branch} />
      {run.pull_request?.html_url ? (
        <a className="pr-link" href={run.pull_request.html_url} target="_blank" rel="noreferrer">
          Open PR #{run.pull_request.number}
        </a>
      ) : (
        <p className="muted">A pull request has not been created yet.</p>
      )}
    </div>
  );
}

function FileReview({ files, selectedFile, activeFile, setActiveFile }) {
  return (
    <div className="file-review">
      <div className="file-tabs">
        {files.map((file, index) => (
          <button
            className={index === activeFile ? "active" : ""}
            key={file.path}
            onClick={() => setActiveFile(index)}
            type="button"
          >
            {file.path.split("/").pop()}
          </button>
        ))}
      </div>
      <div className="code-meta">
        <code>{selectedFile?.path}</code>
        <span>{selectedFile?.rationale}</span>
      </div>
      <pre className="code-view"><code>{selectedFile?.content}</code></pre>
    </div>
  );
}

function InfoRow({ label, value }) {
  return (
    <div className="info-row">
      <span>{label}</span>
      <strong>{value || "Not available"}</strong>
    </div>
  );
}

function StageIcon({ status }) {
  if (status === "complete") return <Check size={17} />;
  if (status === "running") return <Loader2 className="spin" size={17} />;
  if (status === "failed") return <AlertCircle size={17} />;
  if (status === "skipped") return <Clock size={17} />;
  if (status === "waiting") return <Clock size={17} />;
  return <Clock size={17} />;
}

function StatusPill({ status = "pending" }) {
  return <span className={`status-pill ${status}`}>{status}</span>;
}

function defaultStages(busy) {
  return [
    { id: "request", label: "Request received", status: busy ? "complete" : "pending", detail: "Enter repository and scenario details." },
    { id: "clone", label: "Clone repository", status: busy ? "running" : "pending", detail: "Temporary GitHub workspace." },
    { id: "analyze", label: "Analyze reuse", status: "pending", detail: "Find existing tests and reusable code." },
    { id: "crawl", label: "Crawl web app", status: "pending", detail: "Collect UI evidence for new web tests." },
    { id: "generate", label: "Generate proposal", status: "pending", detail: "Create only required files." },
    { id: "review", label: "Human review", status: "pending", detail: "Review generated scripts." },
    { id: "approve", label: "Approval", status: "pending", detail: "Approve before commit and PR." },
    { id: "validate", label: "Run validation", status: "pending", detail: "Run generated test commands." },
    { id: "commit", label: "Commit changes", status: "pending", detail: "Commit approved scripts." },
    { id: "push", label: "Push branch", status: "pending", detail: "Push generated branch." },
    { id: "pr", label: "Open pull request", status: "pending", detail: "Raise GitHub PR." },
  ];
}

function firstInterestingStage(run) {
  const stages = run?.stages ?? [];
  return (
    stages.find((stage) => stage.status === "failed")?.id
    ?? stages.find((stage) => stage.status === "waiting")?.id
    ?? stages.find((stage) => stage.id === "analyze")?.id
    ?? stages[0]?.id
    ?? "request"
  );
}

function getApprovalDisabledReason(run, proposedFiles) {
  if (!run) return "";
  if (run.status === "pull_request_created") return "A pull request has already been created for this run.";
  if (run.result?.decision === "reuse_existing") {
    return "This scenario is already automated, so there are no generated files to approve.";
  }
  if (run.result?.decision === "needs_clarification") {
    return "Clarify the scenario and rerun before approval.";
  }
  if (run.result?.decision !== "generate") return "Approval is available only after generation.";
  if (proposedFiles.length === 0) return "The generated proposal does not contain files.";
  return "";
}

createRoot(document.getElementById("root")).render(<App />);
