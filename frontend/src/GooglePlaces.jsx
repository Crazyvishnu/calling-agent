import React, { useEffect, useState } from 'react';
import { api } from './api';
export default function GooglePlaces() {
  const [status,setStatus]=useState(null),[query,setQuery]=useState('Restaurants in Hyderabad');
  const [approved,setApproved]=useState(false),[busy,setBusy]=useState(false),[result,setResult]=useState(null),[error,setError]=useState('');
  useEffect(()=>{api('/google-places/status').then(setStatus).catch(e=>setError(e.message));},[]);
  async function search(e) {
    e.preventDefault();setBusy(true);setResult(null);setError('');
    try{setResult(await api('/google-places/search','POST',{query,cost_acknowledged:approved}));}
    catch(e){setError(e.message);}
    finally{setBusy(false);setApproved(false);api('/google-places/status').then(setStatus).catch(()=>{});}
  }
  return <section className="panel setup-card"><h2>Google Maps research</h2><p>Optional owner-approved Google Places search returns identifiers and links. Review each business on Google Maps. Listings do not grant contact consent, and business details are not imported into your CRM.</p>
    <p>{status?.configured?'Configured · '+status.remaining_requests+' requests remaining in the rolling 24-hour quota.':'Disabled until you configure Google API access, review its terms and explicitly approve billing and a request quota.'}</p>
    <form onSubmit={search}><label>Search query<input value={query} onChange={e=>setQuery(e.target.value)} minLength={3} maxLength={160} required/></label>
      <label className="check-label"><input type="checkbox" checked={approved} onChange={e=>setApproved(e.target.checked)}/><span>I approve this provider request and understand my Google account’s pricing applies.</span></label>
      <button className="secondary" disabled={busy||!status?.configured||!approved||!status.remaining_requests}>{busy?'Searching…':'Search Google Places'}</button></form>
    {error&&<p className="error" role="alert">{error}</p>}
    {result&&<div><img src="https://maps.gstatic.com/mapfiles/api-3/images/powered-by-google-on-white3.png" alt="Powered by Google" width="120" height="14"/><ul>{result.results.map((r,i)=><li key={r.place_id}><a href={r.maps_url} target="_blank" rel="noopener noreferrer">Review result {i+1} on Google Maps</a></li>)}</ul>{!result.results.length&&<p>No results found.</p>}</div>}
    <p><a href="https://policies.google.com/terms" target="_blank" rel="noopener noreferrer">Google terms</a> · <a href="https://policies.google.com/privacy" target="_blank" rel="noopener noreferrer">Google privacy</a></p>
  </section>;
}
