# -*- coding: utf-8 -*-
import logging
import uuid
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)

class StudentCourseEnrollment(models.Model):
    _name = 'siswa.kursus.enrollment'
    _description = 'Pendaftaran Kursus Siswa'
    _order = 'tanggal_mulai desc'

    name = fields.Char(string="Pendaftaran", compute='_compute_name', store=True)
    
    siswa_id = fields.Many2one(
        'm.siswa', 
        string='Siswa', 
        required=True, 
        ondelete='cascade',
        index=True
    )
    modul_id = fields.Many2one(
        'modul.pembelajaran', 
        string='Kursus/Modul', 
        required=True
    )
    tanggal_mulai = fields.Date(
        string='Tanggal Mulai', 
        default=fields.Date.context_today,
        required=True
    )
    tanggal_selesai = fields.Date(string='Tanggal Selesai')
    
    status = fields.Selection([
        ('aktif', 'Aktif'),
        ('lulus', 'Lulus'),
        ('berhenti', 'Berhenti')
    ], string='Status', default='aktif', required=True)

    access_code = fields.Char(
        string='Kode Akses Ujian',
        copy=False,
        readonly=True,
        help='Kode akses yang digenerate untuk siswa login di Student Dashboard',
        groups='students.group_student_trainer',
    )
    access_code_active = fields.Boolean(
        string='Kode Akses Aktif',
        default=False,
        copy=False,
        groups='students.group_student_trainer',
    )

    jumlah_pertemuan_wajib = fields.Integer(
        string="Sesi Wajib",
        compute='_compute_jumlah_pertemuan_wajib',
        store=True
    )

    # Field ini akan diisi oleh modul absensi_siswa
    _sql_constraints = [
        ('enrollment_unique', 'unique(siswa_id, modul_id)', 'Siswa sudah terdaftar di kursus ini!')
    ]

    penilaian_ids = fields.One2many(
        'siswa.kursus.penilaian.sertifikat',
        'enrollment_id',
        string='Penilaian Sertifikat'
    )

    average_score = fields.Float(
        string='Rata-rata Nilai',
        related='penilaian_ids.average_score',
        store=True,
        readonly=True
    )

    assessment_line_ids = fields.One2many(
        string='Detail Penilaian',
        related='penilaian_ids.assessment_line_ids',
        readonly=True
    )
    
    exam_ids = fields.One2many(
        'siswa.kursus.exam',
        'enrollment_id',
        string='Ujian Siswa'
    )

    # Dihitung dari absensi_siswa (sudah ada di enrollment_extension, tapi kita pastikan di sini)
    jumlah_pertemuan_diikuti = fields.Integer(
        string="Pertemuan Diikuti",
        compute='_compute_jumlah_pertemuan_diikuti',
        store=True
    )

    @api.depends('modul_id') # In actual use, this will depend on absensi records
    def _compute_jumlah_pertemuan_diikuti(self):
        # This will be handled by absensi_siswa module extension
        # But we ensure it's here for the logic
        pass

    def action_generate_access_code(self):
        self.ensure_one()
        code = 'ST-' + uuid.uuid4().hex[:6].upper()
        self.write({
            'access_code': code,
            'access_code_active': True,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Kode Akses Berhasil Digenerate'),
                'message': _('Kode akses untuk siswa: %s') % code,
                'sticky': True,
                'type': 'success',
            }
        }

    def action_deactivate_access_code(self):
        self.ensure_one()
        self.write({'access_code_active': False})

    def action_start_exam(self, selected_types=None):
        self.ensure_one()
        try:
            import random
            _logger.info(f"Starting exam for enrollment {self.id}")
            
            # Check attendance
            attended = self.jumlah_pertemuan_diikuti or 0
            required = self.jumlah_pertemuan_wajib or 0
            
            if attended < required:
                raise UserError(_(f"Siswa belum menyelesaikan semua pertemuan wajib ({attended}/{required})."))
            
            if not self.modul_id:
                raise UserError(_("Modul pembelajaran belum ditentukan."))
            
            # Auto-generate and activate access code on student level
            student = self.siswa_id
            if not student.access_code or not student.access_code_active:
                student.action_generate_access_code()
            # Also keep enrollment-level code for backward compat
            if not self.access_code or not self.access_code_active:
                self.action_generate_access_code()

            created_count = 0
            for exam_template in self.modul_id.exam_ids:
                # If selected_types is provided, only create those
                if selected_types and exam_template.exam_type not in selected_types:
                    continue

                existing_attempts = self.env['siswa.kursus.exam'].search_count([
                    ('enrollment_id', '=', self.id),
                    ('exam_type', '=', exam_template.exam_type)
                ])
                attempt_number = existing_attempts + 1

                new_exam = self.env['siswa.kursus.exam'].create({
                    'enrollment_id': self.id,
                    'exam_type': exam_template.exam_type,
                    'time_limit_minutes': exam_template.time_limit_minutes,
                    'attempt_number': attempt_number,
                })
                
                # Shuffle questions
                lines_to_copy = list(exam_template.line_ids)
                random.shuffle(lines_to_copy)
                
                for idx, line in enumerate(lines_to_copy, 1):
                    self.env['siswa.kursus.exam.line'].create({
                        'exam_id': new_exam.id,
                        'sequence': idx,
                        'question': line.question,
                        'category_name': line.category_id.name,
                        'option_a': line.option_a,
                        'option_b': line.option_b,
                        'option_c': line.option_c,
                        'option_d': line.option_d,
                        'option_a_url': line.option_a_url,
                        'option_b_url': line.option_b_url,
                        'option_c_url': line.option_c_url,
                        'option_d_url': line.option_d_url,
                        'correct_option': line.correct_option,
                        'practice': line.practice,
                        'description': line.description,
                        'project_url': line.project_url,
                        'media_url': line.media_url,
                        'media_type': line.media_type,
                    })
                created_count += 1

            return self.action_view_student_exams()
            
        except Exception as e:
            _logger.error(f"Error in action_start_exam: {str(e)}")
            raise

    def action_view_student_exams(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('students.action_siswa_kursus_exam')
        action['domain'] = [('enrollment_id', '=', self.id)]
        action['context'] = {'default_enrollment_id': self.id}
        return action
    
    # Fields and methods moved from enrollment_extension for direct availability
    has_certificate_assessment = fields.Boolean(
        string="Ada Penilaian Sertifikat",
        compute="_compute_has_certificate_assessment",
        store=False # No need to store, computed on-the-fly
    )

    @api.depends('status') 
    def _compute_has_certificate_assessment(self):
        for rec in self:
            rec.has_certificate_assessment = bool(self.env['siswa.kursus.penilaian.sertifikat'].search([('enrollment_id', '=', rec.id)], limit=1))

    def action_create_or_view_certificate_assessment(self):
        self.ensure_one()
        
        # Search for existing assessment
        existing_assessment = self.env['siswa.kursus.penilaian.sertifikat'].search([('enrollment_id', '=', self.id)], limit=1)
        
        action = self.env['ir.actions.act_window']._for_xml_id('students.action_siswa_kursus_penilaian_sertifikat')
        
        if existing_assessment:
            action['res_id'] = existing_assessment.id
            action['views'] = [(False, 'form')] 
            return action

        # Create new assessment
        new_assessment = self.env['siswa.kursus.penilaian.sertifikat'].create({
            'enrollment_id': self.id,
        })

        # Pre-fill assessment lines from modul.pembelajaran.penilaian.item
        if self.modul_id and self.modul_id.penilaian_item_ids:
            for item in self.modul_id.penilaian_item_ids:
                self.env['siswa.kursus.penilaian.sertifikat.line'].create({
                    'assessment_id': new_assessment.id,
                    'penilaian_item_id': item.id,
                    'sequence': item.sequence,
                    'score': 0.0,
                })
        
        action['res_id'] = new_assessment.id
        action['views'] = [(False, 'form')]
        return action

    @api.depends('siswa_id.name', 'modul_id.name')
    def _compute_name(self):
        for rec in self:
            if rec.siswa_id and rec.modul_id:
                rec.name = f"{rec.siswa_id.name} - {rec.modul_id.name}"
            else:
                rec.name = "Pendaftaran Baru"

    @api.depends('modul_id.materi_ids')
    def _compute_jumlah_pertemuan_wajib(self):
        for rec in self:
            if rec.modul_id:
                rec.jumlah_pertemuan_wajib = len(rec.modul_id.materi_ids)
            else:
                rec.jumlah_pertemuan_wajib = 0
