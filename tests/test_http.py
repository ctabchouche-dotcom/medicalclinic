# -*- coding: utf-8 -*-
import re
from datetime import timedelta

import pytz

from odoo import fields
from odoo.tests.common import HttpCase, tagged

from odoo.addons.medicalclinic.controllers.booking import WEEKDAYS


def _public_local(env, value):
    tzname = env.company.partner_id.tz or 'Africa/Algiers'
    return pytz.UTC.localize(value).astimezone(pytz.timezone(tzname))


@tagged('post_install', '-at_install')
class TestClinicHttp(HttpCase):

    def _open(self, url, data=None):
        if not getattr(self, 'session', None):
            self.authenticate(None, None)
        return self.url_open(url, data=data)

    def test_booking_page_shows_a_confirmed_hour_then_creates_a_draft(self):
        doctor = self.env['clinic.doctor'].create({
            'name': 'Dr Http Confirme',
            'specialty': 'Orthopédie',
            'consultation_fee': 2000,
        })
        hidden = self.env['clinic.doctor'].create({
            'name': 'Dr Http Brouillon',
            'specialty': 'Généraliste',
            'consultation_fee': 1500,
        })
        start = (fields.Datetime.now() + timedelta(days=12)).replace(
            hour=10, minute=0, second=0, microsecond=0,
        )
        draft = self.env['clinic.slot'].create({
            'doctor_id': hidden.id,
            'start': start,
            'stop': start + timedelta(minutes=30),
        })
        slot = self.env['clinic.slot'].create({
            'doctor_id': doctor.id,
            'start': start + timedelta(hours=1),
            'stop': start + timedelta(hours=1, minutes=30),
        })
        slot.action_send()
        closed = self._open('/prendre-rendez-vous')
        self.assertEqual(closed.status_code, 200)
        self.assertNotIn(doctor.name, closed.text)
        self.assertNotIn(hidden.name, closed.text)

        slot.action_confirm()
        local = _public_local(self.env, slot.start)
        day = local.strftime('%Y-%m-%d')
        opened = self._open('/prendre-rendez-vous?doctor_id=%s' % doctor.id)
        self.assertEqual(opened.status_code, 200)
        self.assertIn(doctor.name, opened.text)
        self.assertNotIn(hidden.name, opened.text)
        self.assertIn(day, opened.text)
        self.assertNotIn('name="slot_id"', opened.text)

        chosen = self._open('/prendre-rendez-vous?doctor_id=%s&day=%s' % (doctor.id, day))
        self.assertIn('%s %s' % (WEEKDAYS[local.weekday()], local.strftime('%d/%m')), chosen.text)
        self.assertIn(local.strftime('%H:%M'), chosen.text)
        self.assertIn('value="%s"' % slot.id, chosen.text)
        token = re.search(r'name="csrf_token" value="([^"]+)"', chosen.text)
        self.assertTrue(token)
        sent = self._open('/prendre-rendez-vous/envoyer', data={
            'csrf_token': token.group(1),
            'slot_id': str(slot.id),
            'patient_name': 'Samir Khelifi',
            'phone': '0555121212',
            'gender': 'male',
            'notes': 'Douleur au genou',
        })
        self.assertEqual(sent.status_code, 200)
        self.assertIn('Demande envoyée', sent.text)
        appointment = self.env['clinic.appointment'].search([
            ('slot_id', '=', slot.id),
            ('booked_online', '=', True),
        ])
        self.assertEqual(appointment.state, 'draft')
        self.assertEqual(draft.state, 'draft')
        self.assertFalse(draft.appointment_id)

    def test_lab_results_require_the_access_token(self):
        doctor = self.env['clinic.doctor'].create({
            'name': 'Dr Http Labo',
            'specialty': 'Biologie',
            'consultation_fee': 1000,
        })
        patient = self.env['clinic.patient'].create({
            'name': 'Amina Http',
            'gender': 'female',
            'phone': '0555000333',
        })
        lab = self.env['clinic.lab.request'].create({
            'patient_id': patient.id,
            'doctor_id': doctor.id,
            'check_glycemie': True,
        })
        line = lab.line_ids.filtered(lambda item: item.analyte_code == 'glu')
        line.result = '1,40'
        missing = self._open('/lab/results/%s' % lab.id)
        self.assertEqual(missing.status_code, 404)
        wrong = self._open('/lab/results/%s?access_token=not-the-token' % lab.id)
        self.assertEqual(wrong.status_code, 404)
        opened = self._open('/lab/results/%s?access_token=%s' % (lab.id, lab.access_token))
        self.assertEqual(opened.status_code, 200)
        self.assertIn(patient.name, opened.text)
        self.assertIn('au laboratoire', opened.text)
        self.assertNotIn('1,40', opened.text)
