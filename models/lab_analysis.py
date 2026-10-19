# -*- coding: utf-8 -*-
import base64
import logging
import uuid
from io import BytesIO
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

try:
    import qrcode
except ImportError:
    qrcode = None


class ClinicLabRequest(models.Model):
    _name = 'clinic.lab.request'
    _description = "Demande d'Analyse Laboratoire"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Référence',
        required=True,
        readonly=True,
        default=lambda self: _('Nouveau'),
    )
    patient_id = fields.Many2one(
        'clinic.patient', string='Patient', required=True, tracking=True
    )

    # LIEN DIRECT AVEC LE MODÈLE CLINIC.DOCTOR (ET NON RES.USERS / RES.PARTNER)
    doctor_id = fields.Many2one(
        'clinic.doctor',
        string='Médecin Prescripteur',
        required=True,
        tracking=True,
    )

    appointment_id = fields.Many2one(
        'clinic.appointment', string='Rendez-vous associé'
    )
    date = fields.Datetime(
        string='Date de demande', default=fields.Datetime.now
    )
    state = fields.Selection(
        [
            ('draft', 'Brouillon (Demande)'),
            ('in_progress', 'En cours (Laboratoire)'),
            ('done', 'Terminé / Résultats Prêts'),
        ],
        string='Statut',
        default='draft',
        tracking=True,
        group_expand=True,
    )

    # check, code, libellé, détail affiché au médecin
    EXAM_SPECS = (
        ('check_nfs', 'nfs', 'NFS / Numération formule sanguine',
         'Hématies, hémoglobine, hématocrite, VGM, TCMH, CCMH, leucocytes, formule, plaquettes'),
        ('check_glycemie', 'glycemie', 'Glycémie à jeun',
         'Glucose'),
        ('check_cholesterol', 'lipidique', 'Bilan lipidique',
         'Cholestérol total, HDL, LDL, triglycérides'),
        ('check_renal', 'renal', 'Bilan rénal',
         'Urée, créatinine, DFG'),
        ('check_bilan_hepatique', 'hepatique', 'Bilan hépatique',
         'ASAT, ALAT, GGT, phosphatases alcalines, bilirubine totale et conjuguée'),
        ('check_bilan_hormonal', 'hormonal', 'Bilan hormonal',
         'FSH, LH, œstradiol, AMH, prolactine, TSH, testostérone'),
        ('check_bilan_ionique', 'ionique', 'Bilan ionique',
         'Sodium, potassium, chlorures, bicarbonates, calcium'),
    )
    _STATE_TRANSITIONS = {
        'draft': {'in_progress'},
        'in_progress': {'done', 'draft'},
        'done': {'in_progress'},
    }

    # --- SÉCURITÉ & QR CODE ---
    access_token = fields.Char(
        string='Access Token', default=lambda self: str(uuid.uuid4()), copy=False
    )
    qr_code = fields.Binary(
        string='QR Code', compute='_compute_qr_code', store=True
    )
    result_url = fields.Char(
        string='URL des résultats', compute='_compute_result_url'
    )

    # --- CASES À COCHER (SÉLECTION PAR LE MÉDECIN) ---
    check_nfs = fields.Boolean(string='NFS / Numération formule sanguine')
    check_glycemie = fields.Boolean(string='Glycémie à jeun')
    check_cholesterol = fields.Boolean(string='Bilan lipidique')
    check_renal = fields.Boolean(string='Bilan rénal')
    check_bilan_hepatique = fields.Boolean(string='Bilan hépatique')
    check_bilan_hormonal = fields.Boolean(string='Bilan hormonal')
    check_bilan_ionique = fields.Boolean(string='Bilan ionique')
    line_ids = fields.One2many(
        'clinic.lab.result.line', 'request_id', string='Paramètres', copy=False,
    )

    notes = fields.Text(string='Remarques du laboratoire')

    @api.depends('access_token')
    def _compute_result_url(self):
        base_url = (
            self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        )
        for rec in self:
            if rec.id and rec.access_token:
                rec.result_url = f'{base_url}/lab/results/{rec.id}?access_token={rec.access_token}'
            else:
                rec.result_url = False

    @api.depends('result_url')
    def _compute_qr_code(self):
        for rec in self:
            if qrcode and rec.result_url:
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=4,
                    border=2,
                )
                qr.add_data(rec.result_url)
                qr.make(fit=True)
                img = qr.make_image(fill_color='black', back_color='white')
                temp = BytesIO()
                img.save(temp, format='PNG')
                rec.qr_code = base64.b64encode(temp.getvalue())
            else:
                rec.qr_code = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nouveau')) == _('Nouveau'):
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('clinic.lab.request')
                    or _('Nouveau')
                )
        records = super().create(vals_list)
        records._sync_result_lines()
        return records

    def read(self, fields=None, load='_classic_read'):
        wants_lines = fields is None or 'line_ids' in fields
        stored = self.filtered(lambda rec: isinstance(rec.id, int))
        if wants_lines and stored and not self.env.context.get('clinic_skip_sync'):
            try:
                stored.with_context(clinic_skip_sync=True)._sync_result_lines()
            except AccessError:
                pass
        return super(ClinicLabRequest, self.with_context(clinic_skip_sync=True)).read(fields, load=load)

    def exam_lines(self):
        self.ensure_one()
        self._sync_result_lines()
        rows = []
        for line in self.line_ids:
            rows.append({
                'id': line.id,
                'exam': line.exam_name,
                'label': line.name,
                'value': line.result or '',
                'unit': line.unit or '',
                'reference': line.reference or '',
                'note': line.ref_note or '',
                'flag': line.flag or '',
                'flag_label': dict(line._fields['flag'].selection).get(line.flag, ''),
            })
        return rows

    def exam_summary(self):
        self.ensure_one()
        labels = [label for check, _code, label, _detail in self.EXAM_SPECS if self[check]]
        return ', '.join(labels) or _("Aucun examen")

    def _merged_flag(self, vals, field_name):
        if field_name in vals:
            return bool(vals[field_name])
        return bool(self[field_name])

    def _selected_exam_codes(self, vals=None):
        self.ensure_one()
        vals = vals or {}
        return [
            code
            for check, code, _label, _detail in self.EXAM_SPECS
            if self._merged_flag(vals, check)
        ]

    def _has_exam(self, vals=None):
        self.ensure_one()
        return bool(self._selected_exam_codes(vals))

    def _missing_results(self):
        self.ensure_one()
        return [
            '%s — %s' % (line.exam_name, line.name)
            for line in self.line_ids
            if not str(line.result or '').strip()
        ]

    def _sync_result_lines(self):
        Line = self.env['clinic.lab.result.line'].sudo()
        catalog = self.env['clinic.lab.result.line'].ANALYTES
        for rec in self:
            if not isinstance(rec.id, int):
                continue
            selected = set(rec._selected_exam_codes())
            obsolete = rec.line_ids.filtered(lambda line: line.exam_code not in selected)
            if obsolete:
                obsolete.sudo().unlink()
                rec.invalidate_recordset(['line_ids'])
            existing = set(rec.line_ids.mapped('analyte_code'))
            to_create = []
            sequence = 0
            for _check, exam_code, exam_name, _detail in self.EXAM_SPECS:
                if exam_code not in selected:
                    continue
                for analyte in catalog[exam_code]:
                    sequence += 10
                    if analyte['code'] in existing:
                        continue
                    to_create.append({
                        'request_id': rec.id,
                        'exam_code': exam_code,
                        'exam_name': exam_name,
                        'analyte_code': analyte['code'],
                        'sequence': sequence,
                        'name': analyte['name'],
                        'unit': analyte['unit'],
                    })
            if to_create:
                Line.create(to_create)
                rec.invalidate_recordset(['line_ids'])

    def write(self, vals):
        new_state = vals.get('state')
        if new_state == 'in_progress':
            for rec in self:
                if rec.state != 'in_progress' and not rec._has_exam(vals):
                    raise UserError(_("Cochez au moins un examen avant d'envoyer au laboratoire."))
        becoming_done = self.browse()
        if new_state == 'done':
            becoming_done = self.filtered(lambda rec: rec.state != 'done')
        result = super().write(vals)
        if new_state or any(key.startswith('check_') for key in vals):
            self._sync_result_lines()
        if becoming_done:
            for rec in becoming_done:
                missing = rec._missing_results()
                if missing:
                    raise UserError(_("Renseignez les résultats : %s") % ', '.join(missing))
        return result

    @api.model
    def _configure_results_mail_template(self):
        template = self.env.ref(
            'medicalclinic.email_template_lab_results', raise_if_not_found=False,
        )
        report = self.env.ref(
            'medicalclinic.action_report_clinic_lab_request', raise_if_not_found=False,
        )
        if not template or not report:
            return
        template.sudo().write({
            'subject': "Vos résultats d'analyses médicales - {{ object.name }}",
            'email_from': self._results_email_from() or '{{ user.email_formatted }}',
            'email_to': '{{ object.patient_id.email }}',
            'use_default_to': False,
            'body_html': """
<div style="font-family: Arial, sans-serif; font-size: 14px; color: #333333;">
    <p>Bonjour <strong t-out="object.patient_id.name or ''">Patient</strong>,</p>
    <p>Vos résultats d'analyses médicales (Réf : <strong t-out="object.name or ''">LAB/001</strong>), prescrits par le <strong>Dr. <t t-out="object.doctor_id.name or ''">Médecin</t></strong>, sont disponibles.</p>
    <p>Le bulletin PDF joint reprend chaque paramètre, son unité, les valeurs de référence et l'interprétation.</p>
    <div style="margin: 25px 0; text-align: center;">
        <a t-att-href="object.result_url or '#'" style="background-color: #00878a; color: #ffffff; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">Consulter mes résultats en ligne</a>
    </div>
    <p>Vous pouvez aussi scanner le QR code figurant sur le bulletin.</p>
    <p>Cordialement,<br/><strong>Le service laboratoire</strong></p>
</div>
""",
            'report_template_ids': [(4, report.id)],
        })

    @api.model
    def _results_email_from(self):
        server = self.env['ir.mail_server'].sudo().search([
            ('active', '=', True),
            ('smtp_user', '!=', False),
        ], order='sequence, id', limit=1)
        if server.smtp_user:
            return server.smtp_user
        return self.env.company.email_formatted or self.env.user.email_formatted or False

    def _send_results_email(self):
        self.ensure_one()
        email = (self.patient_id.email or '').strip()
        if not email:
            raise UserError(_("Ce patient n'a pas d'adresse e-mail."))
        template = self.env.ref(
            'medicalclinic.email_template_lab_results',
            raise_if_not_found=False,
        )
        if not template:
            raise UserError(_("Le modèle d'e-mail des résultats est introuvable."))
        sender = self._results_email_from()
        if not sender:
            raise UserError(_("Aucun serveur d'envoi n'est configuré."))
        self._configure_results_mail_template()
        try:
            mail_id = template.sudo().send_mail(
                self.id,
                force_send=True,
                raise_exception=True,
                email_values={
                    'email_to': email,
                    'email_from': sender,
                },
            )
        except UserError:
            raise
        except Exception as err:
            _logger.exception("Envoi des résultats impossible pour %s", self.name)
            raise UserError(_("L'e-mail n'a pas pu être envoyé : %s") % err) from err
        mail = self.env['mail.mail'].sudo().browse(mail_id)
        if mail.state == 'exception':
            reason = (mail.failure_reason or _("connexion refusée par le serveur mail")).strip()
            raise UserError(_("L'e-mail n'a pas pu être envoyé : %s") % reason)
        return True

    def action_start(self):
        self.action_set_state('in_progress')

    def action_done_and_notify(self):
        self.action_set_state('done')

    def action_set_state(self, new_state):
        labels = dict(self._fields['state'].selection)
        if new_state not in labels:
            raise UserError(_("Statut inconnu."))
        for rec in self:
            if new_state == rec.state:
                continue
            if new_state not in rec._STATE_TRANSITIONS.get(rec.state, ()):
                raise UserError(_("Ce changement de statut n'est pas autorisé."))
            rec.write({'state': new_state})
        return True


class ClinicLabResultLine(models.Model):
    _name = 'clinic.lab.result.line'
    _description = "Paramètre d'analyse"
    _order = 'sequence, id'

    # Bornes adulte (bas, haut). None = borne ouverte. Références courantes des labos français.
    ANALYTES = {
        'nfs': [
            {'code': 'rbc', 'name': 'Hématies', 'unit': 'T/L',
             'male': (4.50, 5.50), 'female': (4.00, 5.00),
             'reference': 'H 4,50–5,50 / F 4,00–5,00'},
            {'code': 'hb', 'name': 'Hémoglobine', 'unit': 'g/dL',
             'male': (13.0, 17.0), 'female': (12.0, 16.0),
             'reference': 'H 13,0–17,0 / F 12,0–16,0'},
            {'code': 'ht', 'name': 'Hématocrite', 'unit': '%',
             'male': (40.0, 50.0), 'female': (37.0, 47.0),
             'reference': 'H 40–50 / F 37–47'},
            {'code': 'mcv', 'name': 'VGM', 'unit': 'fL',
             'male': (80.0, 100.0), 'female': (80.0, 100.0),
             'reference': '80–100'},
            {'code': 'mch', 'name': 'TCMH', 'unit': 'pg',
             'male': (27.0, 32.0), 'female': (27.0, 32.0),
             'reference': '27–32'},
            {'code': 'mchc', 'name': 'CCMH', 'unit': 'g/dL',
             'male': (32.0, 36.0), 'female': (32.0, 36.0),
             'reference': '32–36'},
            {'code': 'wbc', 'name': 'Leucocytes', 'unit': 'G/L',
             'male': (4.0, 10.0), 'female': (4.0, 10.0),
             'reference': '4,0–10,0'},
            {'code': 'neut', 'name': 'Polynucléaires neutrophiles', 'unit': 'G/L',
             'male': (1.8, 7.5), 'female': (1.8, 7.5),
             'reference': '1,8–7,5'},
            {'code': 'lymph', 'name': 'Lymphocytes', 'unit': 'G/L',
             'male': (1.0, 4.0), 'female': (1.0, 4.0),
             'reference': '1,0–4,0'},
            {'code': 'mono', 'name': 'Monocytes', 'unit': 'G/L',
             'male': (0.2, 1.0), 'female': (0.2, 1.0),
             'reference': '0,2–1,0'},
            {'code': 'eos', 'name': 'Polynucléaires éosinophiles', 'unit': 'G/L',
             'male': (0.04, 0.50), 'female': (0.04, 0.50),
             'reference': '0,04–0,50'},
            {'code': 'baso', 'name': 'Polynucléaires basophiles', 'unit': 'G/L',
             'male': (0.0, 0.10), 'female': (0.0, 0.10),
             'reference': '0,00–0,10'},
            {'code': 'plt', 'name': 'Plaquettes', 'unit': 'G/L',
             'male': (150.0, 400.0), 'female': (150.0, 400.0),
             'reference': '150–400'},
        ],
        'glycemie': [
            {'code': 'glu', 'name': 'Glucose', 'unit': 'g/L',
             'male': (0.70, 1.10), 'female': (0.70, 1.10),
             'reference': '0,70–1,10',
             'note': 'À jeun. 1,10–1,25 : hyperglycémie modérée. ≥ 1,26 : diabète.'},
        ],
        'lipidique': [
            {'code': 'ct', 'name': 'Cholestérol total', 'unit': 'g/L',
             'male': (None, 2.00), 'female': (None, 2.00),
             'reference': '< 2,00'},
            {'code': 'hdl', 'name': 'HDL-cholestérol', 'unit': 'g/L',
             'male': (0.40, None), 'female': (0.50, None),
             'reference': 'H > 0,40 / F > 0,50'},
            {'code': 'ldl', 'name': 'LDL-cholestérol', 'unit': 'g/L',
             'male': (None, 1.60), 'female': (None, 1.60),
             'reference': '< 1,60',
             'note': 'Cible selon le risque cardiovasculaire. Friedewald non valable si triglycérides ≥ 4 g/L.'},
            {'code': 'tg', 'name': 'Triglycérides', 'unit': 'g/L',
             'male': (None, 1.50), 'female': (None, 1.50),
             'reference': '< 1,50'},
        ],
        'renal': [
            {'code': 'urea', 'name': 'Urée', 'unit': 'g/L',
             'male': (0.15, 0.45), 'female': (0.15, 0.45),
             'reference': '0,15–0,45'},
            {'code': 'creat', 'name': 'Créatinine', 'unit': 'µmol/L',
             'male': (62.0, 115.0), 'female': (44.0, 80.0),
             'reference': 'H 62–115 / F 44–80',
             'note': 'Équivalent : H 7–13 mg/L, F 5–10 mg/L.'},
            {'code': 'gfr', 'name': 'DFG (CKD-EPI)', 'unit': 'mL/min/1,73 m²',
             'male': (90.0, None), 'female': (90.0, None),
             'reference': '≥ 90'},
        ],
        'hepatique': [
            {'code': 'ast', 'name': 'ASAT (TGO)', 'unit': 'UI/L',
             'male': (None, 40.0), 'female': (None, 32.0),
             'reference': 'H < 40 / F < 32'},
            {'code': 'alt', 'name': 'ALAT (TGP)', 'unit': 'UI/L',
             'male': (None, 41.0), 'female': (None, 33.0),
             'reference': 'H < 41 / F < 33'},
            {'code': 'ggt', 'name': 'GGT', 'unit': 'UI/L',
             'male': (None, 60.0), 'female': (None, 40.0),
             'reference': 'H < 60 / F < 40'},
            {'code': 'alp', 'name': 'Phosphatases alcalines', 'unit': 'UI/L',
             'male': (40.0, 129.0), 'female': (35.0, 104.0),
             'reference': 'H 40–129 / F 35–104'},
            {'code': 'bili_t', 'name': 'Bilirubine totale', 'unit': 'µmol/L',
             'male': (None, 21.0), 'female': (None, 21.0),
             'reference': '< 21'},
            {'code': 'bili_d', 'name': 'Bilirubine conjuguée', 'unit': 'µmol/L',
             'male': (None, 5.0), 'female': (None, 5.0),
             'reference': '< 5'},
        ],
        'hormonal': [
            {'code': 'fsh', 'name': 'FSH', 'unit': 'UI/L',
             'reference': 'Folliculaire 3–10 ; pic 4–25 ; lutéale 1,5–9 ; ménopause > 25',
             'note': 'Interpréter selon la phase du cycle.'},
            {'code': 'lh', 'name': 'LH', 'unit': 'UI/L',
             'reference': 'Folliculaire 2–10 ; pic 15–75 ; lutéale 1–12 ; ménopause > 15',
             'note': 'Interpréter selon la phase du cycle.'},
            {'code': 'e2', 'name': 'Œstradiol', 'unit': 'pg/mL',
             'reference': 'Folliculaire 20–150 ; pic 150–400 ; lutéale 50–250 ; ménopause < 30',
             'note': 'Interpréter selon la phase du cycle.'},
            {'code': 'amh', 'name': 'AMH', 'unit': 'ng/mL', 'kind': 'amh',
             'note': 'Réserve ovarienne basse en dessous d’environ 1,0 ng/mL. Souvent élevée au-delà de 4–5 ng/mL.'},
            {'code': 'prl', 'name': 'Prolactine', 'unit': 'ng/mL',
             'male': (4.0, 15.0), 'female': (5.0, 25.0),
             'reference': 'H 4–15 / F 5–25',
             'note': 'Hors grossesse et hors allaitement. Équivalent : H 80–320 / F 100–500 mUI/L. Contrôler une macroprolactine si la valeur est haute.'},
            {'code': 'tsh', 'name': 'TSH', 'unit': 'mUI/L',
             'male': (0.40, 4.00), 'female': (0.40, 4.00),
             'reference': '0,40–4,00',
             'note': 'Grossesse : 1er trimestre 0,1–2,5 ; 2e 0,2–3,0 ; 3e 0,3–3,5 mUI/L.'},
            {'code': 'testo', 'name': 'Testostérone totale', 'unit': 'ng/mL',
             'male': (2.5, 8.5), 'female': (0.15, 0.70),
             'reference': 'H 2,5–8,5 / F 0,15–0,70',
             'note': 'Équivalent : H 8,7–29 / F 0,5–2,4 nmol/L.'},
        ],
        'ionique': [
            {'code': 'na', 'name': 'Sodium', 'unit': 'mmol/L',
             'male': (136.0, 145.0), 'female': (136.0, 145.0),
             'reference': '136–145'},
            {'code': 'k', 'name': 'Potassium', 'unit': 'mmol/L',
             'male': (3.5, 5.1), 'female': (3.5, 5.1),
             'reference': '3,5–5,1'},
            {'code': 'cl', 'name': 'Chlorures', 'unit': 'mmol/L',
             'male': (98.0, 107.0), 'female': (98.0, 107.0),
             'reference': '98–107'},
            {'code': 'hco3', 'name': 'Bicarbonates', 'unit': 'mmol/L',
             'male': (22.0, 29.0), 'female': (22.0, 29.0),
             'reference': '22–29'},
            {'code': 'ca', 'name': 'Calcium', 'unit': 'mmol/L',
             'male': (2.20, 2.55), 'female': (2.20, 2.55),
             'reference': '2,20–2,55',
             'note': 'Soit 88–102 mg/L. Si l’albumine est anormale : Ca corrigé = Ca + 0,02 × (40 − albumine en g/L).'},
        ],
    }
    _AMH_BANDS = (
        (18, 25, 1.5, 7.0, '18–25 ans : 1,5–7,0'),
        (26, 30, 1.2, 6.0, '26–30 ans : 1,2–6,0'),
        (31, 35, 0.8, 5.0, '31–35 ans : 0,8–5,0'),
        (36, 40, 0.4, 3.5, '36–40 ans : 0,4–3,5'),
        (41, 45, 0.1, 2.0, '41–45 ans : 0,1–2,0'),
        (46, 120, None, 1.0, '> 45 ans : < 1,0'),
    )

    request_id = fields.Many2one(
        'clinic.lab.request', string='Demande', required=True, ondelete='cascade', index=True,
    )
    sequence = fields.Integer(default=10)
    exam_code = fields.Char(required=True, index=True)
    exam_name = fields.Char(string='Bilan', required=True)
    analyte_code = fields.Char(required=True, index=True)
    name = fields.Char(string='Paramètre', required=True)
    unit = fields.Char(string='Unité')
    result = fields.Char(string='Résultat')
    reference = fields.Char(string='Valeurs de référence', compute='_compute_interpretation', store=True)
    ref_note = fields.Char(string='Commentaire de norme', compute='_compute_interpretation', store=True)
    flag = fields.Selection(
        [('normal', 'Normal'), ('high', 'Haut'), ('low', 'Bas')],
        string='Interprétation',
        compute='_compute_interpretation',
        store=True,
    )

    _analyte_uniq = models.Constraint(
        'UNIQUE(request_id, analyte_code)',
        "Ce paramètre est déjà sur la demande.",
    )

    def _analyte(self):
        self.ensure_one()
        for analyte in self.ANALYTES.get(self.exam_code, []):
            if analyte['code'] == self.analyte_code:
                return analyte
        return {}

    def _amh_bounds(self, patient):
        if not patient or patient.gender != 'female' or not patient.age:
            return None, None, False
        for low_age, high_age, low, high, label in self._AMH_BANDS:
            if low_age <= patient.age <= high_age:
                return low, high, label
        return None, None, False

    def _bounds(self, analyte, patient):
        if analyte.get('kind') == 'amh':
            low, high, _label = self._amh_bounds(patient)
            return low, high
        gender = patient.gender if patient and patient.gender in ('male', 'female') else 'female'
        low, high = analyte.get(gender, (None, None))
        return low, high

    def _reference_text(self, analyte, patient):
        if analyte.get('kind') == 'amh':
            _low, _high, label = self._amh_bounds(patient)
            if label:
                return label
            if patient and patient.gender == 'male':
                return 'Dosage de réserve ovarienne, non interprétable chez l’homme'
            return ' ; '.join(band[4] for band in self._AMH_BANDS)
        return analyte.get('reference') or ''

    @staticmethod
    def _parse_result(value):
        text = (value or '').strip().replace(' ', '').replace(',', '.')
        for prefix in ('<=', '>=', '<', '>', '='):
            if text.startswith(prefix):
                text = text[len(prefix):]
                break
        try:
            return float(text)
        except ValueError:
            return None

    @api.depends(
        'result', 'analyte_code', 'exam_code',
        'request_id.patient_id.gender', 'request_id.patient_id.age',
    )
    def _compute_interpretation(self):
        for line in self:
            analyte = line._analyte()
            patient = line.request_id.patient_id
            line.reference = line._reference_text(analyte, patient)
            line.ref_note = analyte.get('note') or False
            number = line._parse_result(line.result)
            low, high = line._bounds(analyte, patient)
            if number is None or (low is None and high is None):
                line.flag = False
            elif low is not None and number < low:
                line.flag = 'low'
            elif high is not None and number > high:
                line.flag = 'high'
            else:
                line.flag = 'normal'