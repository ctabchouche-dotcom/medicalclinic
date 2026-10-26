# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestClinicSecurity(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_a = new_test_user(
            cls.env, login='doctor.a', groups='medicalclinic.group_clinic_doctor',
        )
        cls.user_b = new_test_user(
            cls.env, login='doctor.b', groups='medicalclinic.group_clinic_doctor',
        )
        cls.reception = new_test_user(
            cls.env, login='reception.clinic', groups='medicalclinic.group_clinic_receptionist',
        )
        cls.lab_user = new_test_user(
            cls.env, login='lab.clinic', groups='medicalclinic.group_clinic_lab',
        )
        cls.doctor_a = cls.env['clinic.doctor'].create({
            'name': 'Dr Amrani',
            'specialty': 'Orthopédie',
            'consultation_fee': 2500,
            'user_id': cls.user_a.id,
        })
        cls.doctor_b = cls.env['clinic.doctor'].create({
            'name': 'Dr Belkacem',
            'specialty': 'Généraliste',
            'consultation_fee': 1500,
            'user_id': cls.user_b.id,
        })
        cls.patient = cls.env['clinic.patient'].create({
            'name': 'Amina Benali',
            'gender': 'female',
            'phone': '0555000111',
        })

    def test_a_doctor_only_sees_their_own_records(self):
        slot_a, slot_b = self._pair('clinic.slot', {})
        appointment_a, appointment_b = self._pair('clinic.appointment', {})
        lab_a, lab_b = self._pair('clinic.lab.request', {'check_glycemie': True})
        radio_a, radio_b = self._pair('clinic.radiology.request', {
            'region': 'knee',
            'side': 'right',
        })
        as_a = self.env(user=self.user_a)
        for own, other in (
            (slot_a, slot_b),
            (appointment_a, appointment_b),
            (lab_a, lab_b),
            (radio_a, radio_b),
        ):
            visible = as_a[own._name].search([])
            self.assertIn(own, visible)
            self.assertNotIn(other, visible)
            with self.assertRaises(AccessError):
                other.with_user(self.user_a).read(['id'])

    def test_reception_sees_every_draft_appointment(self):
        appointment_a, appointment_b = self._pair('clinic.appointment', {})
        visible = self.env['clinic.appointment'].with_user(self.reception).search([
            ('state', '=', 'draft'),
        ])
        self.assertIn(appointment_a, visible)
        self.assertIn(appointment_b, visible)

    def test_a_doctor_cannot_create_a_slot(self):
        with self.assertRaises(AccessError):
            self.env['clinic.slot'].with_user(self.user_a).create({
                'doctor_id': self.doctor_a.id,
                'start': '2030-01-06 09:00:00',
                'stop': '2030-01-06 09:30:00',
            })

    def test_the_lab_cannot_change_a_prescription(self):
        drug = self.env['clinic.medication'].create({
            'name': 'Paracétamol',
            'strength': '500 mg',
            'form': 'tablet',
            'route': 'oral',
            'drug_class': 'analgesic',
        })
        prescription = self.env['clinic.prescription'].create({
            'patient_id': self.patient.id,
            'doctor_id': self.doctor_a.id,
            'line_ids': [(0, 0, {
                'medication_id': drug.id,
                'dosage': '1 comprimé',
            })],
        })
        with self.assertRaises(AccessError):
            prescription.with_user(self.lab_user).write({'notes': 'Modifié par le laboratoire'})
        self.assertFalse(prescription.notes)

    def _pair(self, model, extra):
        records = self.env[model]
        for doctor in (self.doctor_a, self.doctor_b):
            values = {
                'patient_id': self.patient.id,
                'doctor_id': doctor.id,
            }
            values.update(extra)
            if model == 'clinic.slot':
                values.pop('patient_id')
                values.update({
                    'start': '2030-01-06 09:00:00' if doctor == self.doctor_a else '2030-01-06 10:00:00',
                    'stop': '2030-01-06 09:30:00' if doctor == self.doctor_a else '2030-01-06 10:30:00',
                })
            records |= self.env[model].create(values)
        return records
