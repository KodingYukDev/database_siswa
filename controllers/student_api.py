# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime, timedelta
from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


class StudentExamAPIController(http.Controller):

    def _validate_access_code(self, access_code):
        """
        Validate access code.
        New approach: access_code is on m.siswa (prefix ST-).
        Legacy: access_code on siswa.kursus.enrollment (prefix EXM- or ST- on enrollment).
        Returns (student, enrollment) tuple or (False, False).
        """
        if not access_code:
            return False, False

        # New: try student-level access code first (ST- prefix)
        student = request.env['m.siswa'].sudo().search([
            ('access_code', '=', access_code),
            ('access_code_active', '=', True),
        ], limit=1)
        if student:
            # Prefer an active enrollment for live classes. If the student has
            # graduated and the access code is still active, keep the dashboard
            # available as a learning archive from the latest enrollment.
            enrollment = request.env['siswa.kursus.enrollment'].sudo().search([
                ('siswa_id', '=', student.id),
                ('status', '=', 'aktif'),
            ], order='tanggal_mulai desc', limit=1)
            if not enrollment:
                enrollment = request.env['siswa.kursus.enrollment'].sudo().search([
                    ('siswa_id', '=', student.id),
                ], order='tanggal_mulai desc', limit=1)
            return student, enrollment

        # Legacy: try enrollment-level access code (EXM- or old ST- on enrollment)
        enrollment = request.env['siswa.kursus.enrollment'].sudo().search([
            ('access_code', '=', access_code),
            ('access_code_active', '=', True),
        ], limit=1)
        if enrollment:
            return enrollment.siswa_id, enrollment

        return False, False

    # ----------------------------------------------------------------
    # SCHOOL BRIDGE HELPERS
    # A student registered via the school flow (tipe ekskul) has no
    # siswa.kursus.enrollment. Their exams live on sekolah.kursus.exam,
    # reachable through sekolah.exam.participant.siswa_id. These helpers
    # let the student API surface that data under the same ST- code.
    # ----------------------------------------------------------------
    def _get_school_participant(self, student):
        """Return the most recent school exam participant for a student (or empty recordset)."""
        if not student:
            return request.env['sekolah.exam.participant'].sudo()
        return request.env['sekolah.exam.participant'].sudo().search(
            [('siswa_id', '=', student.id)], order='create_date desc', limit=1
        )

    def _exam_remaining_seconds(self, exam, is_school):
        """Shared remaining-time calc; marks exam done on timeout (model-aware)."""
        remaining_seconds = 0
        if exam.start_time and exam.time_limit_minutes and exam.state == 'in_progress':
            elapsed = (fields.Datetime.now() - exam.start_time).total_seconds()
            total_limit = exam.time_limit_minutes * 60
            if elapsed >= total_limit:
                if is_school:
                    exam.write({'state': 'done', 'completion_status': 'timeout'})
                else:
                    exam.action_done(status='timeout')
                remaining_seconds = 0
            else:
                remaining_seconds = max(0, total_limit - elapsed)
        elif exam.state == 'done':
            remaining_seconds = 0
        elif exam.state == 'draft':
            time_config = request.env['exam.time.config'].sudo().search([('exam_type', '=', exam.exam_type)], limit=1)
            remaining_seconds = (exam.time_limit_minutes if exam.time_limit_minutes else (time_config.duration_minutes if time_config else 30)) * 60
        return int(remaining_seconds)

    def _format_exam(self, exam, is_school):
        """Normalize a siswa/sekolah exam record into the shared JSON shape."""
        return {
            'id': exam.id,
            'display_name': exam.display_name,
            'exam_type': exam.exam_type,
            'tanggal_ujian': str(exam.tanggal_ujian) if getattr(exam, 'tanggal_ujian', False) else '',
            'total_score': exam.total_score,
            'state': exam.state,
            'start_time': str(exam.start_time) if exam.start_time else '',
            'time_limit_minutes': exam.time_limit_minutes,
            'remaining_seconds': self._exam_remaining_seconds(exam, is_school),
            'attempt_number': getattr(exam, 'attempt_number', 1) or 1,
            'source': 'school' if is_school else 'student',
        }

    def _collect_student_exams(self, enrollment, participant):
        """Union of private (enrollment) + school (participant) exams."""
        exams = []
        if enrollment:
            for exam in enrollment.exam_ids:
                exams.append(self._format_exam(exam, is_school=False))
        if participant:
            for exam in participant.exam_ids:
                exams.append(self._format_exam(exam, is_school=True))
        return exams

    def _find_student_exam(self, student, enrollment, exam_id):
        """Locate an exam owned by this student across both models.
        Returns (exam_recordset, is_school)."""
        exam_id = int(exam_id)
        if enrollment:
            exam = request.env['siswa.kursus.exam'].sudo().search(
                [('id', '=', exam_id), ('enrollment_id', '=', enrollment.id)], limit=1
            )
            if exam:
                return exam, False
        participant = self._get_school_participant(student)
        if participant:
            exam = request.env['sekolah.kursus.exam'].sudo().search(
                [('id', '=', exam_id), ('participant_id', '=', participant.id)], limit=1
            )
            if exam:
                return exam, True
        return request.env['siswa.kursus.exam'].sudo(), False

    def _school_attendance_history(self, student):
        """Fallback attendance for ekskul students, sourced from absensi.sekolah."""
        lines = request.env['absensi.sekolah.absensi.line'].sudo().search(
            [('student_id', '=', student.id)], order='id asc'
        )
        status_map = {'hadir': 'hadir', 'sakit': 'izin', 'izin': 'izin', 'tidak_hadir': 'absen'}
        summary = {'total_hadir': 0, 'total_izin': 0, 'total_absen': 0,
                   'total_pertemuan': len(lines), 'pertemuan_ke_berapa': 0}
        history = []
        for idx, line in enumerate(lines, start=1):
            status = status_map.get(line.status, 'belum')
            if status == 'hadir':
                summary['total_hadir'] += 1
            elif status == 'izin':
                summary['total_izin'] += 1
            elif status == 'absen':
                summary['total_absen'] += 1
            summary['pertemuan_ke_berapa'] += 1
            session = line.absensi_id
            history.append({
                'id': line.id,
                'pertemuan_ke': idx,
                'display_name': session.display_name if session else f'Pertemuan {idx}',
                'status': status,
                'tanggal_waktu': str(session.tanggal) if session and session.tanggal else '',
                'notes': line.notes or '',
            })
        return summary, history

    # ----------------------------------------------------------------
    # UNIFIED LOGIN: Supports Staff, Students, and General Hosting Users
    # ----------------------------------------------------------------
    @http.route(['/api/v1/auth/login'], type='json', auth='public', methods=['POST'], csrf=False, cors='*')
    def unified_login(self, **kwargs):
        try:
            login = kwargs.get('login')
            password = kwargs.get('password')
            api_key = kwargs.get('api_key')

            expected_key = request.env['ir.config_parameter'].sudo().get_param('ky_dev.api_key')
            if api_key and expected_key and api_key != expected_key:
                return {'success': False, 'error': 'Invalid API Key'}

            if not login or not password:
                return {'success': False, 'error': 'Login and password are required'}

            # Try Odoo standard authentication (covers Staff, Portal, etc.)
            db = request.session.db
            try:
                uid = request.session.authenticate(db, login, password)
                if uid:
                    user = request.env['res.users'].sudo().browse(uid)
                    
                    # 1. Check for Admin role (Manager group)
                    is_admin = user.has_group('students.group_student_manager') or \
                               user.has_group('database_siswa.group_student_manager') or \
                               user.has_group('kodingyukid_database_siswa.group_student_manager')
                    
                    # 2. Check for Student status (for discount eligibility)
                    # We check if their partner is linked to an active m.siswa record
                    is_student = False
                    Siswa = request.env.get('m.siswa')
                    if Siswa:
                        student_rec = Siswa.sudo().search([
                            ('parent_id', '=', user.partner_id.id),
                            ('status', '=', 'active')
                        ], limit=1)
                        is_student = bool(student_rec)

                    return {
                        'success': True,
                        'role': 'ADMIN' if is_admin else 'USER',
                        'is_student': is_student,
                        'user': {
                            'id': user.id,
                            'name': user.name,
                            'email': user.login,
                        }
                    }
            except Exception:
                # Odoo auth failed
                pass

            return {'success': False, 'error': 'Invalid login or password'}

        except Exception as e:
            _logger.error(f"Unified Login Error: {e}")
            return {'success': False, 'error': str(e)}

    # ----------------------------------------------------------------
    # REGISTER: Create a new Portal User in Odoo
    # ----------------------------------------------------------------
    @http.route(['/api/v1/auth/register'], type='json', auth='public', methods=['POST'], csrf=False, cors='*')
    def student_register(self, **kwargs):
        try:
            name = kwargs.get('name')
            email = kwargs.get('email')
            password = kwargs.get('password')
            api_key = kwargs.get('api_key')

            expected_key = request.env['ir.config_parameter'].sudo().get_param('ky_dev.api_key')
            if api_key and expected_key and api_key != expected_key:
                return {'success': False, 'error': 'Invalid API Key'}

            if not name or not email or not password:
                return {'success': False, 'error': 'Name, email, and password are required'}

            # Check if user already exists
            User = request.env['res.users'].sudo()
            existing = User.search([('login', '=', email)], limit=1)
            if existing:
                return {'success': False, 'error': 'Email sudah terdaftar'}

            # Create Portal User
            # We use the signup template logic if possible, or create manually
            partner = request.env['res.partner'].sudo().create({
                'name': name,
                'email': email,
                'type': 'contact',
            })
            
            user = User.create({
                'name': name,
                'login': email,
                'partner_id': partner.id,
                'password': password,
                'groups_id': [(6, 0, [request.env.ref('base.group_portal').id])]
            })

            return {
                'success': True,
                'user': {
                    'id': user.id,
                    'name': user.name,
                    'email': user.login,
                }
            }

        except Exception as e:
            _logger.error(f"Register Error: {e}")
            return {'success': False, 'error': str(e)}

    # ----------------------------------------------------------------
    # OTP: Generate and Verify
    # ----------------------------------------------------------------
    @http.route(['/api/v1/auth/otp/generate'], type='json', auth='public', methods=['POST'], csrf=False, cors='*')
    def generate_otp(self, **kwargs):
        try:
            email = kwargs.get('email')
            api_key = kwargs.get('api_key')
            
            expected_key = request.env['ir.config_parameter'].sudo().get_param('ky_dev.api_key')
            if api_key and expected_key and api_key != expected_key:
                return {'success': False, 'error': 'Invalid API Key'}

            if not email:
                return {'success': False, 'error': 'Email is required'}

            otp = request.env['ky.otp'].sudo().generate_otp(email)
            return {'success': True, 'otp': otp}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route(['/api/v1/auth/otp/verify'], type='json', auth='public', methods=['POST'], csrf=False, cors='*')
    def verify_otp(self, **kwargs):
        try:
            email = kwargs.get('email')
            otp = kwargs.get('otp')
            api_key = kwargs.get('api_key')

            expected_key = request.env['ir.config_parameter'].sudo().get_param('ky_dev.api_key')
            if api_key and expected_key and api_key != expected_key:
                return {'success': False, 'error': 'Invalid API Key'}

            if not email or not otp:
                return {'success': False, 'error': 'Email and OTP are required'}

            valid = request.env['ky.otp'].sudo().verify_otp(email, otp)
            return {'success': valid}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ----------------------------------------------------------------
    # LOGIN: Validate access code, return enrollment + student + exams
    # ----------------------------------------------------------------
    @http.route(['/api/v1/student/login', '/api/v1/student/login/'], type='json', auth='public', methods=['POST'], csrf=False, cors='*')
    def student_login(self, **kwargs):
        try:
            # For type='json', Odoo automatically parses params into kwargs
            access_code = kwargs.get('access_code', '').strip().upper()

            student, enrollment = self._validate_access_code(access_code)
            if not student:
                return {'success': False, 'error': 'Kode akses tidak valid atau sudah tidak aktif.'}

            # School-origin students have no siswa enrollment but do have a
            # sekolah.exam.participant; bridge to their school exams.
            participant = self._get_school_participant(student)
            if not enrollment and not participant:
                return {'success': False, 'error': 'Siswa belum memiliki kursus aktif.'}

            modul = enrollment.modul_id if enrollment else (participant.modul_id if participant else False)
            exams = self._collect_student_exams(enrollment, participant)

            res = {
                'success': True,
                'enrollment': {
                    'id': enrollment.id if enrollment else 0,
                    'name': enrollment.name if enrollment else (participant.enrollment_id.name if participant else ''),
                    'modul_name': modul.name if modul else '',
                    'modul_id': modul.id if modul else 0,
                    'status': enrollment.status if enrollment else 'aktif',
                },
                'student': {
                    'id': student.id,
                    'name': student.name,
                },
                'exams': exams,
            }
            return res

        except Exception as e:
            _logger.error(f"Student Login Error: {e}")
            return {'success': False, 'error': str(e)}

    # ----------------------------------------------------------------
    # DASHBOARD DATA: Full data for the student dashboard
    # ----------------------------------------------------------------
    @http.route(['/api/v1/student/dashboard_data', '/api/v1/student/dashboard_data/'], type='json', auth='public', methods=['POST'], csrf=False, cors='*')
    def student_dashboard_data(self, **kwargs):
        try:
            access_code = kwargs.get('access_code', '').strip().upper()

            student, enrollment = self._validate_access_code(access_code)
            if not student:
                return {'success': False, 'error': 'Kode akses tidak valid.'}

            participant = self._get_school_participant(student)
            if not enrollment and not participant:
                return {'success': False, 'error': 'Siswa belum memiliki kursus aktif.'}

            modul = enrollment.modul_id if enrollment else (participant.modul_id if participant else False)

            # 1. Profile Data
            profile = {
                'id': student.id,
                'name': student.name,
                'nis': student.nis or '',
                'email': student.email or '',
                'class_name': student.class_name or '',
                'level_name': student.level_id.name if student.level_id else '',
                'class_type_name': student.class_type_id.name if student.class_type_id else '',
                'tipe_siswa': student.tipe_siswa,
                'join_date': str(student.join_date) if student.join_date else '',
                'status': student.status,
                'bio': student.bio_singkat or '',
                'profile_image_url': student.profile_image_url or '',
                'schedule': {
                    'day': dict(student._fields['jadwal_hari'].selection).get(student.jadwal_hari, '') if student.jadwal_hari else '',
                    'time': student.jadwal_jam or 0,
                },
            }

            # 1b. School identity is useful to a student, while billing and
            # staff-only fields remain intentionally private.
            school = getattr(student, 'sekolah_id', False)
            school_data = {
                'name': school.name if school else '',
                'level_name': school.level_id.name if school and school.level_id else '',
                'class_type_name': school.class_type_id.name if school and school.class_type_id else '',
            }

            # 2. Attendance Data
            absensi_rec = request.env['absensi.siswa.absensi'].sudo().search([('enrollment_id', '=', enrollment.id)], limit=1) if enrollment else request.env['absensi.siswa.absensi'].sudo()
            attendance_summary = {
                'total_hadir': 0,
                'total_izin': 0,
                'total_absen': 0,
                'total_pertemuan': 0,
                'pertemuan_ke_berapa': 0,
            }
            attendance_history = []

            if not absensi_rec and participant:
                # Ekskul student: attendance lives in absensi.sekolah
                attendance_summary, attendance_history = self._school_attendance_history(student)
            elif absensi_rec:
                attendance_summary['total_pertemuan'] = absensi_rec.pertemuan_count
                for line in absensi_rec.attendance_line_ids:
                    if line.status == 'hadir': attendance_summary['total_hadir'] += 1
                    elif line.status == 'izin': attendance_summary['total_izin'] += 1
                    elif line.status == 'absen': attendance_summary['total_absen'] += 1
                    
                    if line.status:
                        attendance_summary['pertemuan_ke_berapa'] += 1
                    
                    attendance_history.append({
                        'id': line.id,
                        'pertemuan_ke': line.pertemuan_ke,
                        'display_name': line.display_name,
                        'status': line.status or 'belum',
                        'tanggal_waktu': str(line.tanggal_waktu) if line.tanggal_waktu else '',
                        'notes': line.notes or '',
                    })

            # 3. Certification / Performance
            penilaian_rec = request.env['siswa.kursus.penilaian.sertifikat'].sudo().search([('enrollment_id', '=', enrollment.id)], limit=1) if enrollment else request.env['siswa.kursus.penilaian.sertifikat'].sudo()
            if not penilaian_rec and enrollment:
                penilaian_rec = request.env['siswa.kursus.penilaian.sertifikat'].sudo().search([
                    ('siswa_id', '=', student.id),
                ], order='id desc', limit=1)
            if not enrollment and participant and request.env.get('sekolah.kursus.penilaian.sertifikat'):
                penilaian_rec = request.env['sekolah.kursus.penilaian.sertifikat'].sudo().search([
                    ('participant_id', '=', participant.id),
                ], limit=1)
                if not penilaian_rec:
                    penilaian_rec = request.env['sekolah.kursus.penilaian.sertifikat'].sudo().search([
                        ('student_profile_id', '=', student.id),
                    ], order='id desc', limit=1)
            performance = {
                'total_score': penilaian_rec.total_score if penilaian_rec else 0,
                'average_score': penilaian_rec.average_score if penilaian_rec else 0,
                'state': penilaian_rec.state if penilaian_rec else 'draft',
                'lines': []
            }
            if penilaian_rec:
                for line in penilaian_rec.assessment_line_ids:
                    performance['lines'].append({
                        'name': line.name,
                        'score': line.score,
                    })

            # 3b. Portfolio is student-facing data. Internal module documents
            # must never be exposed through the student dashboard API.
            def _safe_field(record, field_name, default=''):
                return record[field_name] if record and field_name in record._fields else default

            portfolio = []
            portfolio_model = request.env.get('student.portfolio.project')
            projects = portfolio_model.sudo().search([('siswa_id', '=', student.id)], order='create_date desc') if portfolio_model else student.portfolio_project_ids
            for project in projects:
                media_records = project.media_ids if 'media_ids' in project._fields else []
                portfolio.append({
                    'id': project.id,
                    'name': _safe_field(project, 'name'),
                    'description': _safe_field(project, 'description'),
                    'category': _safe_field(project, 'category_name_mapped') or _safe_field(project, 'category'),
                    'project_url': _safe_field(project, 'project_url'),
                    'media': [
                        {'type': _safe_field(media, 'media_type'), 'url': _safe_field(media, 'file_url'), 'name': _safe_field(media, 'file_name')}
                        for media in media_records if _safe_field(media, 'file_url')
                    ],
                })

            certificate = {
                'available': bool(penilaian_rec),
                'state': penilaian_rec.state if penilaian_rec else 'draft',
                'letter': getattr(penilaian_rec, 'nilai_huruf_letter', '') if penilaian_rec else '',
                'label': getattr(penilaian_rec, 'nilai_huruf', '') if penilaian_rec else '',
                'note': getattr(penilaian_rec, 'catatan', '') if penilaian_rec else '',
                'semester': getattr(penilaian_rec, 'semester', '') if penilaian_rec else '',
                'academic_year': getattr(penilaian_rec, 'tahun_ajaran', '') if penilaian_rec else '',
            }

            # 4. Exam List (private enrollment + school participant)
            exams = self._collect_student_exams(enrollment, participant)
            if not performance['lines']:
                performance['lines'] = [
                    {'name': exam['display_name'], 'score': exam['total_score']}
                    for exam in exams if exam.get('total_score', 0) > 0
                ]
                if performance['lines']:
                    scores = [line['score'] for line in performance['lines']]
                    performance['total_score'] = sum(scores)
                    performance['average_score'] = sum(scores) / len(scores)

            res = {
                'success': True,
                'profile': profile,
                'attendance_summary': attendance_summary,
                'attendance_history': attendance_history,
                'performance': performance,
                'certificate': certificate,
                'portfolio': portfolio,
                'school': school_data,
                'exams': exams,
                'enrollment': {
                    'id': enrollment.id if enrollment else 0,
                    'name': enrollment.name if enrollment else (participant.enrollment_id.name if participant else ''),
                    'modul_name': modul.name if modul else '',
                    'status': enrollment.status if enrollment else 'aktif',
                    'start_date': str(enrollment.tanggal_mulai) if enrollment and enrollment.tanggal_mulai else '',
                    'end_date': str(enrollment.tanggal_selesai) if enrollment and enrollment.tanggal_selesai else '',
                    'required_sessions': enrollment.jumlah_pertemuan_wajib if enrollment else 0,
                    'attended_sessions': enrollment.jumlah_pertemuan_diikuti if enrollment else attendance_summary['total_hadir'],
                }
            }
            return res

        except Exception as e:
            _logger.error(f"Dashboard Data Error: {e}")
            return {'success': False, 'error': str(e)}

    # ----------------------------------------------------------------
    # EXAM DETAIL: Get exam questions/lines
    # ----------------------------------------------------------------
    @http.route(['/api/v1/student/exam/detail', '/api/v1/student/exam/detail/'], type='json', auth='public', methods=['POST'], csrf=False, cors='*')
    def exam_detail(self, **kwargs):
        try:
            access_code = kwargs.get('access_code', '').strip().upper()
            exam_id = kwargs.get('exam_id')

            student, enrollment = self._validate_access_code(access_code)
            if not student:
                return {'success': False, 'error': 'Kode akses tidak valid.'}

            exam, is_school = self._find_student_exam(student, enrollment, exam_id)
            if not exam:
                return {'success': False, 'error': 'Ujian tidak ditemukan.'}

            remaining_seconds = self._exam_remaining_seconds(exam, is_school)

            lines = []
            for line in exam.line_ids:
                line_data = {
                    'id': line.id,
                    'sequence': line.sequence,
                    'question': line.question or '',
                    'category_name': line.category_name or '',
                    'option_a': line.option_a or '',
                    'option_b': line.option_b or '',
                    'option_c': line.option_c or '',
                    'option_d': line.option_d or '',
                    'option_a_url': getattr(line, 'option_a_url', '') or '',
                    'option_b_url': getattr(line, 'option_b_url', '') or '',
                    'option_c_url': getattr(line, 'option_c_url', '') or '',
                    'option_d_url': getattr(line, 'option_d_url', '') or '',
                    'practice': line.practice or '',
                    'description': line.description or '',
                    'media_url': line.media_url or '',
                    'media_type': line.media_type or '',
                    'student_answer_selection': line.student_answer_selection or '',
                    'student_answer_text': line.student_answer_text or '',
                    'trainer_status': line.trainer_status or '',
                    'trainer_note': line.trainer_note or '',
                    'score': line.score,
                    'is_correct': line.is_correct,
                }
                lines.append(line_data)

            res = {
                'success': True,
                'exam': {
                    'id': exam.id,
                    'display_name': exam.display_name,
                    'exam_type': exam.exam_type,
                    'state': exam.state,
                    'total_score': exam.total_score,
                    'start_time': str(exam.start_time) if exam.start_time else '',
                    'time_limit_minutes': exam.time_limit_minutes,
                    'remaining_seconds': int(remaining_seconds),
                },
                'lines': lines,
            }
            return res

        except Exception as e:
            _logger.error(f"Exam Detail Error: {e}")
            return {'success': False, 'error': str(e)}

    # ----------------------------------------------------------------
    # START EXAM: Set state to in_progress, record start_time
    # ----------------------------------------------------------------
    @http.route(['/api/v1/student/exam/start', '/api/v1/student/exam/start/'], type='json', auth='public', methods=['POST'], csrf=False, cors='*')
    def exam_start(self, **kwargs):
        try:
            access_code = kwargs.get('access_code', '').strip().upper()
            exam_id = kwargs.get('exam_id')

            student, enrollment = self._validate_access_code(access_code)
            if not student:
                return {'success': False, 'error': 'Kode akses tidak valid.'}

            exam, is_school = self._find_student_exam(student, enrollment, exam_id)
            if not exam:
                return {'success': False, 'error': 'Ujian tidak ditemukan.'}

            if exam.state == 'done':
                return {'success': False, 'error': 'Ujian sudah selesai.'}

            if exam.state == 'draft':
                if is_school:
                    exam.write({'state': 'in_progress', 'start_time': fields.Datetime.now()})
                else:
                    exam.action_start()

            remaining_seconds = self._exam_remaining_seconds(exam, is_school)
            if exam.state == 'in_progress' and not remaining_seconds and exam.time_limit_minutes:
                # Freshly started; full time
                remaining_seconds = exam.time_limit_minutes * 60

            res = {
                'success': True,
                'start_time': str(exam.start_time),
                'time_limit_minutes': exam.time_limit_minutes,
                'remaining_seconds': int(remaining_seconds),
            }
            return res

        except Exception as e:
            _logger.error(f"Exam Start Error: {e}")
            return {'success': False, 'error': str(e)}

    @http.route(['/api/v1/student/exam/submit', '/api/v1/student/exam/submit/'], type='json', auth='public', methods=['POST'], csrf=False, cors='*')
    def exam_submit(self, **kwargs):
        try:
            access_code = kwargs.get('access_code', '').strip().upper()
            exam_id = kwargs.get('exam_id')
            answers = kwargs.get('answers', [])

            student, enrollment = self._validate_access_code(access_code)
            if not student:
                return {'success': False, 'error': 'Kode akses tidak valid.'}

            exam, is_school = self._find_student_exam(student, enrollment, exam_id)
            if not exam:
                return {'success': False, 'error': 'Ujian tidak ditemukan.'}

            if exam.state == 'done':
                return {'success': False, 'error': 'Ujian sudah selesai, tidak bisa submit lagi.'}

            ExamLine = request.env['sekolah.kursus.exam.line' if is_school else 'siswa.kursus.exam.line'].sudo()
            for ans in answers:
                line_id = ans.get('line_id')
                line = ExamLine.search([('id', '=', int(line_id)), ('exam_id', '=', exam.id)], limit=1)
                if not line:
                    continue
                update_vals = {}
                if exam.exam_type == 'pilihan_ganda':
                    selection = ans.get('answer', '')
                    if selection in ('A', 'B', 'C', 'D'):
                        update_vals['student_answer_selection'] = selection
                elif exam.exam_type == 'essai':
                    text = ans.get('answer', '')
                    update_vals['student_answer_text'] = text
                if update_vals:
                    line.write(update_vals)

            needs_grading = exam.exam_type in ('essai', 'praktik')
            final_state = 'submitted' if needs_grading else 'done'
            if is_school:
                exam.write({'state': final_state, 'completion_status': 'done', 'end_time': fields.Datetime.now()})
            else:
                exam.action_done(status='done')
            return {'success': True, 'total_score': exam.total_score}

        except Exception as e:
            _logger.error(f"Exam Submit Error: {e}")
            return {'success': False, 'error': str(e)}

    @http.route(['/api/v1/student/exam/done', '/api/v1/student/exam/done/'], type='json', auth='public', methods=['POST'], csrf=False, cors='*')
    def exam_done(self, **kwargs):
        try:
            access_code = kwargs.get('access_code', '').strip().upper()
            exam_id = kwargs.get('exam_id')
            student, enrollment = self._validate_access_code(access_code)
            if not student:
                return {'success': False, 'error': 'Kode akses tidak valid.'}
            exam, is_school = self._find_student_exam(student, enrollment, exam_id)
            if not exam:
                return {'success': False, 'error': 'Ujian tidak ditemukan.'}
            if exam.state != 'done':
                if is_school:
                    exam.write({'state': 'submitted', 'completion_status': 'done', 'end_time': fields.Datetime.now()})
                else:
                    exam.action_done(status='timeout')
            return {'success': True}
        except Exception as e:
            _logger.error(f"Exam Done Error: {e}")
            return {'success': False, 'error': str(e)}

    @http.route(['/api/v1/student/time-config', '/api/v1/student/time-config/'], type='json', auth='public', methods=['POST'], csrf=False, cors='*')
    def time_config(self, **kwargs):
        try:
            configs = request.env['exam.time.config'].sudo().search([])
            result = []
            for cfg in configs:
                result.append({'exam_type': cfg.exam_type, 'duration_minutes': cfg.duration_minutes})
            return {'success': True, 'configs': result}
        except Exception as e:
            _logger.error(f"Time Config Error: {e}")
            return {'success': False, 'error': str(e)}
