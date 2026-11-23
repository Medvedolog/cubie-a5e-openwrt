// SPDX-License-Identifier: GPL-2.0-only
'use strict';
'require baseclass';
'require rpc';

var status = rpc.declare({ object: 'luci.a5e-board', method: 'status' });

function cell(label, value) {
	return E('tr', { 'class': 'tr' }, [
		E('td', { 'class': 'td left', 'width': '38%' }, [ label ]),
		E('td', { 'class': 'td left' }, [ value ])
	]);
}

function fmtFreq(khz) {
	return Number.isInteger(khz) && khz > 0 ? _('%.3f MHz').format(khz / 1000) : _('Unavailable');
}

return baseclass.extend({
	title: _('Board'),

	load: function() {
		return L.resolveDefault(status(), null);
	},

	render: function(data) {
		if (!data)
			return E('p', {}, [ _('Board status is unavailable.') ]);
		var sensors = data.temperatures || [], policies = data.policies || [], rows = [];
		sensors.forEach(function(s) {
			if (!Number.isInteger(s.millidegrees))
				return;
			var name = s.label || s.id;
			if (s.source && s.source !== 'thermal')
				name = s.source + ' · ' + name;
			rows.push(cell(_('Temperature') + ': ' + name,
				_('%.1f °C').format(s.millidegrees / 1000)));
		});
		if (!rows.length)
			rows.push(cell(_('Temperature'), _('No kernel temperature sensors reported')));
		policies.forEach(function(p) {
			var label = _('CPU frequency') + ' (' + p.id + ')',
			    value = [ fmtFreq(p.current) ];
			if (Number.isInteger(p.min) && Number.isInteger(p.max))
				value.push(fmtFreq(p.min) + ' – ' + fmtFreq(p.max));
			if (p.governor)
				value.push(p.governor);
			rows.push(cell(label, value.join(' · ')));
		});
		if (!policies.length)
			rows.push(cell(_('CPU frequency'), _('The kernel does not expose CPU frequency policies')));
		return E('table', { 'class': 'table' }, rows);
	}
});
