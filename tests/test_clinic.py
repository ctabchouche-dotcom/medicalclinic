# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestClinic(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.doctor = cls.env['clinic.doctor'].create({
            'name': 'Dr Amrani',
            'specialty': 'Orthopédie',
            'consultation_fee': 2500,
        })
        cls.patient = cls.env['clinic.patient'].create({
            'name': 'Amina Benali',
            'gender': 'female',
            'phone': '0555000111',
        })

    def test_appointment_cannot_skip_confirmation(self):
        appointment = self.env['clinic.appointment'].create({
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
        })
        self.assertEqual(appointment.state, 'draft')
        self.assertTrue(appointment.name.startswith('APT/'))
        with self.assertRaises(UserError):
            appointment.action_done()
        appointment.action_confirm()
        self.assertEqual(appointment.state, 'confirmed')

    def test_public_booking_uses_a_confirmed_slot(self):
        start = fields.Datetime.now() + timedelta(days=3)
        slot = self.env['clinic.slot'].create({
            'doctor_id': self.doctor.id,
            'start': start,
            'stop': start + timedelta(minutes=30),
        })
        with self.assertRaises(UserError):
            self.env['clinic.appointment'].book_public(
                slot.id, 'Samir Khelifi', '0555121212', 'male', notes='Douleur au genou',
            )
        slot.action_send()
        slot.action_confirm()
        appointment = self.env['clinic.appointment'].book_public(
            slot.id, 'Samir Khelifi', '0555121212', 'male', notes='Douleur au genou',
        )
        self.assertEqual(appointment.state, 'draft')
        self.assertTrue(appointment.booked_online)
        self.assertEqual(appointment.slot_id, slot)
        self.assertEqual(slot.appointment_id, appointment)
        self.assertFalse(self.env['clinic.slot'].available_for(self.doctor))
        visible = self.env['clinic.appointment'].search([
            ('state', '=', 'draft'),
            ('booked_online', '=', True),
            ('doctor_id', '=', self.doctor.id),
        ])
        self.assertIn(appointment, visible)

        other = self.env['clinic.slot'].create({
            'doctor_id': self.doctor.id,
            'start': start + timedelta(days=1),
            'stop': start + timedelta(days=1, minutes=30),
        })
        other.action_send()
        other.action_confirm()
        later = self.env['clinic.appointment'].book_public(
            other.id, 'samir khelifi', '0555121212', 'male',
        )
        self.assertEqual(later.patient_id, appointment.patient_id)
        self.assertTrue(later.patient_id.code.startswith('PAT'))

    def test_cancelling_a_booking_frees_the_slot(self):
        start = fields.Datetime.now() + timedelta(days=4)
        slot = self.env['clinic.slot'].create({
            'doctor_id': self.doctor.id,
            'start': start,
            'stop': start + timedelta(minutes=20),
        })
        slot.action_send()
        slot.action_confirm()
        appointment = self.env['clinic.appointment'].book_public(
            slot.id, 'Samir Khelifi', '0555121212', 'male',
        )
        appointment.action_cancel()
        self.assertFalse(slot.appointment_id)
        self.assertIn(slot, self.env['clinic.slot'].available_for(self.doctor))

    def test_week_grid_replaces_only_the_drafts(self):
        start = (fields.Datetime.now() + timedelta(days=6)).replace(minute=0, second=0, microsecond=0)
        week_start = start - timedelta(days=1)
        week_end = week_start + timedelta(days=7)
        Slot = self.env['clinic.slot']
        draft = Slot.create({
            'doctor_id': self.doctor.id,
            'start': start,
            'stop': start + timedelta(minutes=30),
        })
        kept = Slot.create({
            'doctor_id': self.doctor.id,
            'start': start + timedelta(hours=2),
            'stop': start + timedelta(hours=2, minutes=30),
        })
        kept.action_send()
        kept.action_confirm()
        other_doctor = self.env['clinic.doctor'].create({
            'name': 'Dr Belkacem',
            'specialty': 'Généraliste',
            'consultation_fee': 1500,
        })
        other = Slot.create({
            'doctor_id': other_doctor.id,
            'start': start,
            'stop': start + timedelta(minutes=30),
        })
        checked = start + timedelta(hours=4)
        result = Slot.apply_week(self.doctor, week_start, week_end, [checked])
        self.assertEqual(result['created'], 1)
        self.assertEqual(result['removed'], 1)
        self.assertFalse(draft.exists())
        self.assertEqual(kept.state, 'confirmed')
        self.assertTrue(other.exists())
        created = Slot.search([('doctor_id', '=', self.doctor.id), ('start', '=', checked)])
        self.assertEqual(created.state, 'draft')
        self.assertEqual(created.stop, checked + timedelta(minutes=30))

    def test_week_grid_ignores_a_past_hour(self):
        past = (fields.Datetime.now() - timedelta(hours=3)).replace(minute=0, second=0, microsecond=0)
        result = self.env['clinic.slot'].apply_week(
            self.doctor,
            past - timedelta(days=1),
            past + timedelta(days=6),
            [past],
        )
        self.assertEqual(result['created'], 0)
        self.assertEqual(result['skipped_past'], 1)

    def test_doctor_edits_a_sent_slot_then_confirms_it(self):
        start = fields.Datetime.now() + timedelta(days=2)
        slot = self.env['clinic.slot'].create({
            'doctor_id': self.doctor.id,
            'start': start,
            'stop': start + timedelta(minutes=30),
        })
        with self.assertRaises(UserError):
            slot.action_confirm()
        slot.action_send()
        moved = start + timedelta(hours=1)
        slot.update_times(moved, moved + timedelta(minutes=30))
        self.assertEqual(slot.state, 'sent')
        self.assertEqual(slot.start, moved)
        slot.action_confirm()
        self.assertIn(slot, self.env['clinic.slot'].available_for(self.doctor))
        self.assertNotIn(
            slot,
            self.env['clinic.slot'].search([('state', '=', 'sent'), ('doctor_id', '=', self.doctor.id)]),
        )

    def test_a_confirmed_slot_cannot_be_booked_twice(self):
        start = fields.Datetime.now() + timedelta(days=5)
        slot = self.env['clinic.slot'].create({
            'doctor_id': self.doctor.id,
            'start': start,
            'stop': start + timedelta(minutes=30),
        })
        slot.action_send()
        self.assertFalse(self.env['clinic.slot'].available_for(self.doctor))
        slot.action_confirm()
        self.env['clinic.appointment'].book_public(slot.id, 'Samir Khelifi', '0555121212', 'male')
        with self.assertRaises(UserError):
            self.env['clinic.appointment'].book_public(slot.id, 'Nadia Cherif', '0555987654', 'female')

    def test_public_booking_rejects_an_unconfirmed_slot(self):
        start = fields.Datetime.now() - timedelta(hours=2)
        slot = self.env['clinic.slot'].create({
            'doctor_id': self.doctor.id,
            'start': start,
            'stop': start + timedelta(minutes=20),
        })
        with self.assertRaises(UserError):
            slot.action_send()

    def test_prescription_keeps_the_drug_line(self):
        drug = self.env['clinic.medication'].create({
            'name': 'Paracétamol',
            'strength': '500 mg',
            'form': 'tablet',
            'route': 'oral',
            'drug_class': 'analgesic',
        })
        prescription = self.env['clinic.prescription'].create({
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'line_ids': [(0, 0, {
                'medication_id': drug.id,
                'dosage': '1 comprimé 3 fois par jour',
                'duration': '5 jours',
            })],
        })
        self.assertTrue(prescription.name.startswith('ORD/'))
        self.assertEqual(prescription.line_ids.medication_id, drug)

    def test_glucose_above_the_range_is_high(self):
        request = self.env['clinic.lab.request'].create({
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'check_glycemie': True,
        })
        line = request.line_ids
        self.assertEqual(line.analyte_code, 'glu')
        line.result = '1,40'
        self.assertEqual(line.flag, 'high')
        line.result = '0,90'
        self.assertEqual(line.flag, 'normal')
        line.result = '0,50'
        self.assertEqual(line.flag, 'low')

    def test_radiology_image_attaches_to_the_open_request(self):
        exam = self.env['clinic.radiology.request'].create({
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'region': 'knee',
            'side': 'right',
        })
        linked = self.env['clinic.radiology.request'].register_study(
            self.patient.code,
            'http://cabinet.local/images/1',
            '1.2.3',
        )
        self.assertEqual(linked, exam)
        self.assertEqual(linked.state, 'image_received')
        self.assertEqual(linked.study_uid, '1.2.3')

    def test_radiology_image_does_not_attach_to_another_patient(self):
        exam = self.env['clinic.radiology.request'].create({
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'region': 'knee',
            'side': 'left',
        })
        other = self.env['clinic.patient'].create({
            'name': 'Yasmine Boudiaf',
            'gender': 'female',
            'phone': '0555000222',
        })
        with self.assertRaises(UserError):
            self.env['clinic.radiology.request'].register_study(
                other.code, 'http://cabinet.local/images/2', '9.9.9',
            )
        self.assertEqual(exam.state, 'requested')
        self.assertFalse(exam.study_uid)

    def test_week_grid_keeps_a_sent_slot(self):
        start = (fields.Datetime.now() + timedelta(days=8)).replace(minute=0, second=0, microsecond=0)
        slot = self.env['clinic.slot'].create({
            'doctor_id': self.doctor.id,
            'start': start,
            'stop': start + timedelta(minutes=30),
        })
        slot.action_send()
        result = self.env['clinic.slot'].apply_week(
            self.doctor, start - timedelta(days=1), start + timedelta(days=6), [],
        )
        self.assertEqual(result['removed'], 0)
        self.assertEqual(slot.state, 'sent')
        self.assertTrue(slot.exists())

    def test_a_booked_slot_cannot_be_moved(self):
        start = fields.Datetime.now() + timedelta(days=5, hours=3)
        slot = self.env['clinic.slot'].create({
            'doctor_id': self.doctor.id,
            'start': start,
            'stop': start + timedelta(minutes=30),
        })
        slot.action_send()
        slot.action_confirm()
        self.env['clinic.appointment'].book_public(slot.id, 'Samir Khelifi', '0555121212', 'male')
        with self.assertRaises(UserError):
            slot.update_times(start + timedelta(hours=1), start + timedelta(hours=1, minutes=30))
        self.assertEqual(slot.start, start)
