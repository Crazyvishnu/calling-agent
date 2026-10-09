import React, { useEffect, useRef, useState } from 'react';
import { api } from './api';
import GooglePlaces from './GooglePlaces';

export default function Discovery({ onRefresh }) {
  const [config,setConfig]=useState(null),[location,setLocation]=useState('Hyderabad');
  const [latitude,setLatitude]=useState('17.3850'),[longitude,setLongitude]=useState('78.4867');
  const [category,setCategory]=useState('Restaurant'),[radius,setRadius]=useState('2000');
  const [result,setResult]=useState(null),[selected,setSelected]=useState([]),[reviewed,setReviewed]=useState(false);
  const [filter,setFilter]=useState('all'),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const mounted=useRef(false);
  useEffect(()=>{mounted.current=true;api('/discovery/config').then(c=>{if(mounted.current)setConfig(c);}).catch(e=>{if(mounted.current)setError(e.message);});return()=>{mounted.current=false;};},[]);
  async function search(e){
    e.preventDefault();setBusy(true);setError('');setNotice('');setResult(null);setSelected([]);setReviewed(false);
    try{const r=await api('/discovery/search','POST',{location,latitude:Number(latitude),longitude:Number(longitude),category,radius_m:Number(radius)});if(mounted.current)setResult(r);}
    catch(e){if(mounted.current)setError(e.message);}finally{if(mounted.current)setBusy(false);}
  }
  async function importSelected(){
    setBusy(true);setError('');
    try{
      const r=await api('/discovery/import','POST',{search_id:result.search_id,keys:selected,reviewed});
      if(!mounted.current)return;
      const accepted=new Map([...r.imported,...r.skipped_duplicates].map(item=>[item.key,item.lead_id]));
      setResult(old=>({...old,results:old.results.map(item=>({...item,duplicate_lead_id:accepted.get(item.key)||item.duplicate_lead_id}))}));
      setSelected([]);setReviewed(false);setNotice(`${r.imported.length} prospects imported; ${r.skipped_duplicates.length} duplicates skipped. Contact permission remains unverified.`);onRefresh();
    }catch(e){if(mounted.current)setError(e.message);}finally{if(mounted.current)setBusy(false);}
  }
  const visible=result?.results.filter(item=>filter==='all'||item.website_signal==='not_listed')||[];
  function toggle(key){setSelected(old=>old.includes(key)?old.filter(k=>k!==key):old.length<20?[...old,key]:old);setReviewed(false);}
  return <><GooglePlaces/><section className="panel lab-panel discovery-panel">
    <h2>Find business prospects</h2>
    <p className="discovery-intro">Search public OpenStreetMap listings around a location. Review website opportunities, then import selected prospects into your CRM.</p>
    <p className="notice">OpenStreetMap is the connected source. Optional Google Places research is configured separately above. A public listing or phone number does not grant permission to call.</p>
    <form onSubmit={search} className="discovery-form">
      <label>Nearby area <select disabled={busy} defaultValue="Hyderabad" onChange={e=>{const area=config?.locations.find(a=>a.name===e.target.value);if(area){setLocation(area.name);setLatitude(String(area.latitude));setLongitude(String(area.longitude));}}}>
        {(config?.locations||[{name:'Hyderabad'}]).map(area=><option key={area.name}>{area.name}</option>)}<option>Custom coordinates</option>
      </select></label>
      <label>Location label <input required maxLength={100} disabled={busy} value={location} onChange={e=>setLocation(e.target.value)} /></label>
      <label>Latitude <input required type="number" step="any" min="6" max="37" disabled={busy} value={latitude} onChange={e=>setLatitude(e.target.value)} /></label>
      <label>Longitude <input required type="number" step="any" min="68" max="98" disabled={busy} value={longitude} onChange={e=>setLongitude(e.target.value)} /></label>
      <label>Business category <select disabled={busy} value={category} onChange={e=>setCategory(e.target.value)}>{(config?.categories||['Restaurant']).map(c=><option key={c}>{c}</option>)}</select></label>
      <label>Search radius <select disabled={busy} value={radius} onChange={e=>setRadius(e.target.value)}><option value="500">500 metres</option><option value="1000">1 km</option><option value="2000">2 km</option><option value="5000">5 km</option></select></label>
      <button className="primary" disabled={busy||!config}>{busy?'Working…':'Search businesses'}</button>
    </form>
    <p className="discovery-intro">The label does not geocode an address: search uses the coordinates shown. Public servers may be busy. Up to 100 results; search results expire after 15 minutes.</p>
    {error&&<p role="alert" className="error">{error}</p>}
    {notice&&<p role="status" className="notice">{notice}</p>}
    {result&&<>
      <div className="lab-controls"><strong>{result.results.length} records found {result.cached?'· cached':''}</strong>
        <label>Website filter <select value={filter} onChange={e=>{setFilter(e.target.value);setSelected([]);setReviewed(false);}}><option value="all">All records</option><option value="not_listed">Website not listed</option></select></label>
      </div>
      <p className="discovery-intro">Missing website data is an opportunity to review, not proof that a business has no website. Website quality and ownership are not checked.</p>
      {result.may_be_truncated&&<p className="notice">The result cap was reached. Try a smaller radius; this is not a complete business directory.</p>}
      <div className="discovery-results">{visible.map(item=><article className="discovery-card" key={item.key}>
        <label className="check-label"><input type="checkbox" aria-label={`Select ${item.business_name}`} disabled={busy||!!item.duplicate_lead_id||(!selected.includes(item.key)&&selected.length>=20)} checked={selected.includes(item.key)} onChange={()=>toggle(item.key)} /><strong>{item.business_name}</strong></label>
        <p>{item.category} · {item.city} · {item.distance_m} m from search centre</p>
        {item.address&&<p>{item.address}</p>}<p>Public contact: {item.phone||'Not listed'}</p>
        <p>{item.website?<a href={item.website} target="_blank" rel="noopener noreferrer">Visit listed website</a>:item.website_signal==='needs_review'?'Website tag needs manual review':'Website not listed'}</p>
        <a href={item.source_url} target="_blank" rel="noopener noreferrer">OpenStreetMap source record</a>
        {item.duplicate_lead_id&&<p className="notice">Already represented in CRM · lead #{item.duplicate_lead_id}</p>}
      </article>)}</div>
      {!visible.length&&<p className="notice">No records match this search/filter. OSM coverage may be incomplete; try another category or nearby area.</p>}
      <div className="discovery-review"><label className="check-label"><input type="checkbox" checked={reviewed} disabled={busy||!selected.length} onChange={e=>setReviewed(e.target.checked)} />I reviewed the selected business records and their source. Import them for research with contact permission unverified.</label>
        <button className="primary" disabled={busy||!reviewed||!selected.length} onClick={importSelected}>Import {selected.length} selected prospects</button>
      </div>
    </>}
    <p className="discovery-attribution"><a href={config?.license_url||'https://www.openstreetmap.org/copyright'} target="_blank" rel="noopener noreferrer">{config?.attribution||'© OpenStreetMap contributors · ODbL 1.0'}</a></p>
  </section></>;
}
