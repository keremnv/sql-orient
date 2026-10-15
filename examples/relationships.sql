-- Every call relationship touching alpha(), in both directions, with provenance.
SELECT CASE WHEN e.target = 'mod_a_alpha' THEN 'incoming' ELSE 'outgoing' END AS direction,
       s.label AS source, e.relation, t.label AS target,
       e.source_file, e.source_location
FROM g_edges e
JOIN g_nodes s ON s.id = e.source
JOIN g_nodes t ON t.id = e.target
WHERE 'mod_a_alpha' IN (e.source, e.target)
  AND e.relation = 'calls'
ORDER BY direction, e.id;
