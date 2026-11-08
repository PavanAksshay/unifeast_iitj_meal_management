let serviceWindows = [];
const adminHeaders = () => ({'X-Admin-Key': accessToken});
async function adminJson(url, options = {}) {
  const response = await fetch(API + url, {...options, headers: {...adminHeaders(), ...options.headers}});
  const data = await response.json();
  if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Please check the information and try again.');
  return data;
}
async function loadServiceWindows() {
  const dateInput = document.getElementById('service-date');
  if (!dateInput.value) dateInput.value = localDate();
  try {
    serviceWindows = await adminJson('/admin/service-windows?'+new URLSearchParams({service_date: dateInput.value}));
    const past = dateInput.value < localDate();
    document.getElementById('service-window-list').innerHTML = serviceWindows.map((x,i) => `<div class="service-window"><div><strong>${esc(x.meal)}</strong><span class="service-tag ${x.cancelled?'cancelled':''}">${x.cancelled?'Removed':x.source==='date'?'Custom for this date':'Default'}</span><p class="sub">${esc(x.starts_at)} – ${esc(x.ends_at)}</p></div><div class="service-actions"><button class="btn secondary small" ${past?'disabled':''} data-index="${i}" onclick="openServiceWindow(Number(this.dataset.index))">${x.cancelled?'Restore':'Edit'}</button>${x.cancelled?'':`<button class="btn secondary small" ${past?'disabled':''} data-index="${i}" onclick="removeServiceWindow(Number(this.dataset.index))">Remove</button>`}</div></div>`).join('') || '<p class="sub">No meals scheduled for this date.</p>';
    message('service-window-msg', past?'Past service windows are read-only.':'');
  } catch(e) { message('service-window-msg',e.message,'error'); }
}
function openServiceWindow(index) {
  const item = index === undefined ? null : serviceWindows[index];
  const selectedDate = document.getElementById('service-date').value || localDate();
  document.body.insertAdjacentHTML('beforeend', `<div class="admin-modal" id="service-modal"><form class="card" onsubmit="saveServiceWindow(event)"><div class="row"><h2>${item?(item.cancelled?'Restore meal':'Edit meal'):'Add meal'}</h2><button type="button" class="btn secondary" onclick="closeModal('service-modal')">×</button></div><p class="sub">This change applies only to ${esc(selectedDate)}.</p><label class="field">Meal name<input name="meal" required maxlength="20" value="${esc(item?.meal || '')}" ${item?'readonly':''} placeholder="e.g. Special Lunch"></label><div class="row"><label class="field">Starts<input name="starts_at" type="time" required value="${esc(item?.starts_at || '')}"></label><label class="field">Ends<input name="ends_at" type="time" required value="${esc(item?.ends_at || '')}"></label></div><input type="hidden" name="service_date" value="${esc(selectedDate)}"><input type="hidden" name="editing" value="${item?'yes':'no'}"><button class="btn">${item?.cancelled?'Restore meal':'Save meal'}</button><div id="service-modal-msg"></div></form></div>`);
}
async function saveServiceWindow(event) {
  event.preventDefault(); const form=event.currentTarget, data=new FormData(form);
  const body=Object.fromEntries(['meal','service_date','starts_at','ends_at'].map(k=>[k,data.get(k)]));
  try { await adminJson('/admin/service-windows',{method:data.get('editing')==='yes'?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); closeModal('service-modal'); await loadServiceWindows(); loadAdmin(); }
  catch(e){message('service-modal-msg',e.message,'error')}
}
async function removeServiceWindow(index) {
  const item=serviceWindows[index], service_date=document.getElementById('service-date').value;
  if (!confirm(`Remove ${item.meal} on ${service_date}? Students will not be able to collect this meal.`)) return;
  try {await adminJson('/admin/service-windows?'+new URLSearchParams({service_date,meal:item.meal}),{method:'DELETE'});await loadServiceWindows();loadAdmin()}
  catch(e){message('service-window-msg',e.message,'error')}
}
function presenceParams(range) {
  const params=new URLSearchParams({start:range.start,end:range.end});
  for(const [id,key] of [['presence-meal','meal'],['presence-status','status'],['report-course','course'],['report-branch','branch'],['report-roll','roll_number']]) {const value=document.getElementById(id)?.value.trim();if(value)params.set(key,value)}
  return params;
}
function presenceTime(value) { return value ? new Date(value).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',dateStyle:'medium',timeStyle:'short'}) : '—' }
async function loadPresenceDetail(offset=0) {
  const target=document.getElementById('presence-results');
  try {
    const params=presenceParams(reportRange('presence'));params.set('offset',offset);params.set('limit','100');
    const data=await adminJson('/admin/presence?'+params);
    const rows=data.records.map(x=>`<tr><td>${esc(x.date)}</td><td>${esc(x.meal)}</td><td><strong>${esc(x.student_name)}</strong><br>${esc(x.roll_number)}</td><td><span class="presence-status">${esc(x.status)}</span></td><td>${esc(x.token_reference || (x.status==='Collected'?'Unavailable for older records':'—'))}</td><td>${esc(presenceTime(x.token_created_at))}</td><td>${esc(presenceTime(x.token_expires_at))}</td><td>${esc(presenceTime(x.collected_at))}</td><td>${esc(x.mess || '—')}</td><td>${esc(x.collection_source || '—')}</td></tr>`).join('');
    target.innerHTML=`<div class="presence-summary">${Object.entries(data.counts).map(([key,value])=>`<span><strong>${value}</strong> ${esc(key)}</span>`).join('')}</div><p class="sub">Times shown in India Standard Time. ${data.total} matching records.</p><div class="presence-table"><table><thead><tr><th>Date</th><th>Meal</th><th>Student</th><th>Status</th><th>Token reference</th><th>Token created</th><th>Token expires</th><th>Collected</th><th>Mess</th><th>Source</th></tr></thead><tbody>${rows || '<tr><td colspan="10">No matching presence records.</td></tr>'}</tbody></table></div><div class="presence-pagination"><button class="btn secondary small" ${offset===0?'disabled':''} onclick="loadPresenceDetail(${Math.max(0,offset-100)})">Previous</button><span>${data.total?offset+1:0}–${Math.min(offset+100,data.total)} of ${data.total}</span><button class="btn secondary small" ${offset+100>=data.total?'disabled':''} onclick="loadPresenceDetail(${offset+100})">Next</button></div>`;
  } catch(e) {target.innerHTML=`<div class="notice error">${esc(e.message)}</div>`}
}
function parsePresenceCsv(text) {
  const rows=[];let row=[],field='',quoted=false;
  for(let i=0;i<text.length;i++){const c=text[i];if(quoted){if(c==='"'&&text[i+1]==='"'){field+='"';i++}else if(c==='"')quoted=false;else field+=c}else if(c==='"')quoted=true;else if(c===','){row.push(field);field=''}else if(c==='\n'){row.push(field.replace(/\r$/, ''));rows.push(row);row=[];field=''}else field+=c}
  if(field||row.length){row.push(field);rows.push(row)}return rows;
}
async function generatePresenceReport(format,range,printWindow) {
  const response=await fetch(API+'/admin/presence.csv?'+presenceParams(range),{headers:adminHeaders()});
  if(!response.ok){const d=await response.json();throw Error(d.detail||'Presence report unavailable')}
  const blob=await response.blob();
  if(format==='pdf'){
    if(!printWindow)throw Error('Allow pop-ups to print a PDF report.');
    const rows=parsePresenceCsv(await blob.text());
    printWindow.document.write(`<title>Meal Presence Report</title><h1>UniFeast Meal Presence</h1><p>${esc(range.start)} to ${esc(range.end)} · Times are in India Standard Time</p><table border="1" cellspacing="0" cellpadding="6">${rows.map(row=>`<tr>${row.map(v=>`<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</table>`);printWindow.document.close();printWindow.print();
  }else{const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`meal-presence-${range.start}-${range.end}.csv`;a.click();URL.revokeObjectURL(url)}
  rememberReport(`Meal presence · ${range.start} to ${range.end}`);loadGeneratedReports();
}
