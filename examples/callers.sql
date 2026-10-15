SELECT n.label AS caller, e.relation, t.label AS target
FROM g_edges e JOIN g_nodes n ON n.id=e.source
JOIN g_nodes t ON t.id=e.target
WHERE e.target='mod_a_alpha' AND e.relation='calls' ORDER BY e.id;
