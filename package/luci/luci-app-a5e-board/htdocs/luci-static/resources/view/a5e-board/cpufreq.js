// SPDX-License-Identifier: GPL-2.0-only
'use strict';
'require rpc';
'require ui';
'require view';

var status = rpc.declare({ object: 'luci.a5e-board', method: 'status' });
var setGovernor = rpc.declare({
	object: 'luci.a5e-board', method: 'set_governor', params: [ 'policy', 'governor' ]
});
var setLimits = rpc.declare({
	object: 'luci.a5e-board', method: 'set_limits', params: [ 'policy', 'min', 'max' ]
});

function fmtFreq(khz) {
	return Number.isInteger(khz) && khz > 0 ? _('%.3f MHz').format(khz / 1000) : _('Unavailable');
}

function choices(label, options, selected, display) {
	var select = E('select', { 'class': 'cbi-input-select', 'aria-label': label },
		options.map(function(v) { return E('option', { value: String(v) }, [ display(v) ]); }));
	if (options.indexOf(selected) === -1) {
		var prompt = E('option', { value: '', disabled: 'disabled' }, [ _('Choose a value') ]);
		select.insertBefore(prompt, select.firstChild);
		select.value = '';
	} else {
		select.value = String(selected);
	}
	return select;
}

function notice(text) {
	ui.addNotification(null, E('p', {}, [ text ]));
}

function submit(e, cb, controls) {
	e.preventDefault();
	controls.forEach(function(c) { c.disabled = true; });
	return Promise.resolve().then(cb).then(function(r) {
		if (r && r.ok === true) {
			window.location.reload();
			return;
		}
		var errors = {
			invalid: _('Invalid CPU setting.'),
			unavailable: _('That setting is no longer available from the kernel. Reload the page.'),
			busy: _('Another CPU setting is being applied. Try again.'),
			rejected: _('The kernel rejected the change.'),
			readback: _('The kernel reported a different governor after the change. Reload to see the current value.'),
			partial: _('The kernel rejected the change and the previous limits could not be restored. Reload to see the current values.')
		};
		var message = r && Object.prototype.hasOwnProperty.call(errors, r.error)
			? errors[r.error] : _('The CPU setting was not confirmed.');
		notice(message);
		controls.forEach(function(c) { c.disabled = false; });
	}).catch(function() {
		notice(_('The CPU setting was not confirmed. Check permissions and reload the page.'));
		controls.forEach(function(c) { c.disabled = false; });
	});
}

function policyView(p, writable) {
	var governors = Array.isArray(p.governors) ? p.governors : [],
	    freqs = Array.isArray(p.frequencies) ? p.frequencies.filter(function(f) {
		    return Number.isInteger(f) && f > 0;
	    }).sort(function(a, b) { return a - b; }) : [];
	var block = E('section', { 'class': 'cbi-section' }, [
		E('h3', {}, [ p.id + (p.cpus ? ' · ' + _('CPUs: %s').format(p.cpus) : '') ]),
		E('p', {}, [ _('Current: %s · Limits: %s to %s · Governor: %s').format(
			fmtFreq(p.current), fmtFreq(p.min), fmtFreq(p.max), p.governor || _('Unavailable')) ])
	]);
	if (!writable)
		return block;
	if (governors.length) {
		var g = choices(_('Governor'), governors, p.governor, String),
		    gb = E('button', { 'type': 'button', 'class': 'btn cbi-button cbi-button-apply' }, [ _('Set governor') ]);
		gb.addEventListener('click', function(e) {
			if (!g.value) {
				notice(_('Choose a governor reported by the kernel.'));
				return;
			}
			submit(e, function() { return setGovernor(p.id, g.value); }, [ g, gb ]);
		});
		block.appendChild(E('p', {}, [ E('label', {}, [ _('Governor'), ' ', g ]), ' ', gb ]));
	} else {
		block.appendChild(E('p', {}, [ _('Governor control is unavailable for this policy.') ]));
	}
	if (freqs.length && Number.isInteger(p.min) && Number.isInteger(p.max)) {
		var min = choices(_('Minimum'), freqs, p.min, fmtFreq),
		    max = choices(_('Maximum'), freqs, p.max, fmtFreq),
		    fb = E('button', { 'type': 'button', 'class': 'btn cbi-button cbi-button-apply' }, [ _('Set limits') ]);
		fb.addEventListener('click', function(e) {
			var lo = Number(min.value), hi = Number(max.value);
			if (!lo || !hi || lo > hi) {
				notice(_('Choose both frequencies. Minimum must not exceed maximum.'));
				return;
			}
			submit(e, function() { return setLimits(p.id, lo, hi); }, [ min, max, fb ]);
		});
		block.appendChild(E('p', {}, [
			E('label', {}, [ _('Minimum'), ' ', min ]), ' ',
			E('label', {}, [ _('Maximum'), ' ', max ]), ' ', fb
		]));
	} else {
		block.appendChild(E('p', {}, [ _('Frequency limits are unavailable: the kernel does not report a writable frequency table for this policy.') ]));
	}
	return block;
}

return view.extend({
	load: function() {
		return L.resolveDefault(status(), null);
	},

	render: function(data) {
		var writable = L.hasViewPermission() === true,
		    policies = data && Array.isArray(data.policies) ? data.policies : [],
		    rows = [ E('h2', {}, [ _('CPU frequency') ]) ];
		if (!data)
			rows.push(E('p', {}, [ _('CPU status is unavailable.') ]));
		else if (!policies.length)
			rows.push(E('p', {}, [ _('CPU frequency controls are unavailable because the kernel does not expose CPU frequency policies on this board.') ]));
		else {
			rows.push(E('p', {}, [ writable
				? _('Settings apply until reboot. Only values reported by the kernel are available. Thermal protections are unchanged.')
				: _('This account has read-only access to CPU settings.') ]));
			policies.forEach(function(p) { rows.push(policyView(p, writable)); });
		}
		return E('div', {}, rows);
	},

	handleSave: null,
	handleSaveApply: null,
	handleReset: null
});
