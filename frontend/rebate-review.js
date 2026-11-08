/* Rebate uploads are reviewed and decided as a whole batch. */
function rebateReviewHeaders() {
  return { [userRole === 'admin' ? 'X-Admin-Key' : 'X-Finance-Key']: accessToken };
}

function renderRebateReviews(batches, target) {
  if (!batches.length) {
    target.innerHTML = '<div class="rebate-empty">No rebate batches are waiting for review.</div>';
    return;
  }

  target.innerHTML = batches.map((batch, index) => {
    const invalid = Number(batch.summary.invalid || 0);
    const count = Number(batch.summary.valid || 0);
    const rows = (batch.rows || []).map(row => `
      <tr>
        <td>${esc(row.student_name || 'Unknown student')}</td>
        <td>${esc(row.roll_number || '—')}</td>
        <td>${esc(row.start_date || '—')}</td>
        <td>${esc(row.end_date || '—')}</td>
        <td>${esc(row.reason || 'Not specified')}</td>
      </tr>`).join('');
    const issues = (batch.issues || []).map(issue => `<li>Row ${esc(issue.row)}: ${esc(issue.message)}</li>`).join('');
    const disabled = invalid > 0 || count === 0;
    return `<details class="rebate-review-batch" ${index === 0 ? 'open' : ''}>
      <summary>
        <span><strong>${esc(batch.source_name)}</strong><small>${count} valid request${count === 1 ? '' : 's'} · ${invalid} issue${invalid === 1 ? '' : 's'}</small></span>
        <span class="rebate-review-toggle">Review details</span>
      </summary>
      <div class="rebate-review-content">
        <p class="sub">Submitted ${esc(new Date(batch.created_at).toLocaleString('en-IN'))} · Batch ${esc(batch.batch_id)}</p>
        ${rows ? `<div class="rebate-review-table"><table><thead><tr><th>Student</th><th>Roll number</th><th>From</th><th>To</th><th>Reason</th></tr></thead><tbody>${rows}</tbody></table></div>` : '<p class="sub">No valid requests in this batch.</p>'}
        ${issues ? `<div class="notice error"><strong>Resolve these issues before approving:</strong><ul>${issues}</ul></div>` : ''}
        <p class="rebate-review-note">Your decision applies to all ${count} valid request${count === 1 ? '' : 's'} in this upload.</p>
        <div class="rebate-review-actions">
          <button class="btn" type="button" data-batch-id="${esc(batch.batch_id)}" data-count="${count}" ${disabled ? 'disabled' : ''} onclick="decideRebate(this, 'approve')">Approve batch</button>
          <button class="btn secondary" type="button" data-batch-id="${esc(batch.batch_id)}" data-count="${count}" onclick="decideRebate(this, 'reject')">Reject batch</button>
        </div>
      </div>
    </details>`;
  }).join('');
}

async function loadPendingRebates() {
  const target = document.getElementById(userRole === 'admin' ? 'admin-rebate-review' : 'finance-rebates');
  if (!target) return;
  try {
    const response = await fetch(API + '/admin/rebates/pending', { headers: rebateReviewHeaders() });
    const batches = await response.json();
    if (!response.ok) throw Error(batches.detail || 'Could not load rebate reviews');
    renderRebateReviews(batches, target);
    const count = document.getElementById('rebate-review-count');
    if (count && userRole === 'admin') count.textContent = `${batches.length} pending`;
  } catch (error) {
    target.innerHTML = `<div class="notice error">${esc(error.message)}</div>`;
  }
}

function loadFinance() {
  return loadPendingRebates();
}

async function decideRebate(button, action) {
  const batch = button.dataset.batchId;
  const count = Number(button.dataset.count);
  const messageTarget = userRole === 'admin' ? 'rebate-review-msg' : 'finance-msg';
  if (!confirm(`${action === 'approve' ? 'Approve' : 'Reject'} this entire upload of ${count} valid request${count === 1 ? '' : 's'}?`)) return;
  const controls = [...button.closest('.rebate-review-actions').querySelectorAll('button')];
  const previouslyDisabled = controls.map(control => control.disabled);
  controls.forEach(control => { control.disabled = true; });
  try {
    const response = await fetch(API + '/admin/rebates/' + encodeURIComponent(batch) + '/' + action, {
      method: 'POST', headers: rebateReviewHeaders(),
    });
    const data = await response.json();
    if (!response.ok) throw Error(data.detail || 'Could not update the rebate batch');
    message(messageTarget, action === 'approve' ? `Approved ${data.approved_rows} rebate request${data.approved_rows === 1 ? '' : 's'}.` : 'Rebate batch rejected.', 'ok');
    await loadPendingRebates();
    if (userRole === 'admin') await Promise.all([loadRebateHistory(), loadRebateAnalytics()]);
  } catch (error) {
    message(messageTarget, error.message, 'error');
    controls.forEach((control, index) => { control.disabled = previouslyDisabled[index]; });
  }
}
