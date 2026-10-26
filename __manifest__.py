# -*- coding: utf-8 -*-
{
    'name': 'Gestion de Clinique Médicale',
    'version': '1.7.0',
    'summary': 'Système complet de gestion des patients, médecins, consultations et prescriptions',
    'description': """
Module Odoo pour la gestion d'une clinique médicale :
------------------------------------------------------
* Fiches d'informations et dossiers médicaux des Patients
* Profils et spécialités des Médecins
* Prise de Rendez-vous et suivi des consultations
* Prescriptions d'ordonnances
* Sécurité multi-postes adaptée à l'environnement SaaS
* Espace web kanban pour la réception, les médecins et le laboratoire
    """,
    'category': 'Training',
    'author': 'Chakib',
    'website': 'https://www.yourdomain.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'web',
    ],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'security/record_rules.xml',
        'data/sequence.xml',
        'data/lab_sequence.xml',
        'data/prescription_sequence.xml',
        'data/radiology_sequence.xml',
        'data/medication_data.xml',
        'data/mail_template.xml',
        'data/prescription_mail_template.xml',
        'views/patient_view.xml',
        'views/doctor_view.xml',
        'views/appointment_view.xml',
        'views/slot_view.xml',
        'views/lab_view.xml',
        'views/prescription_view.xml',
        'views/radiology_view.xml',
        'views/menu_view.xml',
        'views/portal_templates.xml',
        'views/clinic_web_templates.xml',
        'views/booking_templates.xml',
        'reports/lab_report_action.xml',
        'reports/lab_report.xml',
        'reports/lab_voucher.xml',
        'reports/prescription_report.xml',
        'reports/prescription_report_action.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': True,
}