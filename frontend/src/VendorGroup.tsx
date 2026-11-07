import React, { createContext, useContext, useEffect, useId, useState } from "react";
const GroupVisibility = createContext({ expanded: true, revision: 0 });

export function VendorGroups({ label, children }: { label: string; children: React.ReactNode }) {
  const [visibility, setVisibility] = useState({ expanded: true, revision: 0 });
  return <GroupVisibility.Provider value={visibility}><div className="vendor-groups" aria-label={label}>
    <div className="button-row vendor-visibility" role="group" aria-label={`${label} visibility`}>
      <button type="button" className="secondary" onClick={() => setVisibility(v => ({ expanded: true, revision: v.revision + 1 }))}>Show all vendor groups</button>
      <button type="button" className="quiet" onClick={() => setVisibility(v => ({ expanded: false, revision: v.revision + 1 }))}>Hide all vendor groups</button>
    </div>{children}
  </div></GroupVisibility.Provider>;
}

export function VendorGroup({ title, summary, children }: { title: string; summary?: React.ReactNode; children: React.ReactNode }) {
  const visibility = useContext(GroupVisibility);
  const [expanded, setExpanded] = useState(visibility.expanded);
  useEffect(() => setExpanded(visibility.expanded), [visibility.expanded, visibility.revision]);
  const id = useId();
  return <section className="vendor-assessment-card vendor-collapsible">
    <div className="vendor-group-heading"><h4>{title}</h4>{summary}
      <button type="button" className="quiet" aria-expanded={expanded} aria-controls={id} onClick={() => setExpanded(value => !value)}>
        {expanded ? "Hide" : "Show"} {title} details
      </button>
    </div><div id={id} hidden={!expanded}>{children}</div>
  </section>;
}
