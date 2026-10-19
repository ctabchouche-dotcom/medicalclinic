# -*- coding: utf-8 -*-
import json

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request


class ClinicRadiologyController(http.Controller):

    @http.route('/clinic/radiology/image', type='http', auth='user', methods=['POST'], csrf=False)
    def radiology_image(self, patient_code=None, study_url=None, study_uid=None, **kwargs):
        """Le serveur d'images du cabinet appelle cette adresse quand une radio arrive."""
        user = request.env.user
        if not (
            user.has_group('medicalclinic.group_clinic_manager')
            or user.has_group('medicalclinic.group_clinic_principal')
        ):
            return self._json({'status': 'error', 'message': 'Accès refusé'}, 403)

        if not patient_code:
            payload = request.httprequest.get_json(silent=True) or {}
            patient_code = payload.get('patient_code')
            study_url = study_url or payload.get('study_url')
            study_uid = study_uid or payload.get('study_uid')

        try:
            exam = request.env['clinic.radiology.request'].register_study(
                patient_code, study_url, study_uid,
            )
        except UserError as error:
            return self._json({'status': 'error', 'message': str(error)}, 400)

        return self._json({
            'status': 'ok',
            'id': exam.id,
            'name': exam.name,
            'state': exam.state,
        })

    def _json(self, data, status=200):
        return request.make_response(
            json.dumps(data),
            headers=[('Content-Type', 'application/json')],
            status=status,
        )
