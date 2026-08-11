from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestStudentSecurity(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.internal_user = new_test_user(
            cls.env,
            login='students_internal_test',
            groups='base.group_user',
        )
        cls.viewer_user = new_test_user(
            cls.env,
            login='students_viewer_test',
            groups='students.group_student_viewer',
        )
        cls.trainer_user = new_test_user(
            cls.env,
            login='students_trainer_test',
            groups='students.group_student_trainer',
        )
        cls.manager_user = new_test_user(
            cls.env,
            login='students_manager_test',
            groups='students.group_student_manager',
        )
        cls.student = cls.env['m.siswa'].with_user(cls.manager_user).create({
            'name': 'Student Security Test',
            'password': 'must-not-be-readable',
        })
        cls.learning_module = cls.env['modul.pembelajaran'].create({
            'name': 'Student Security Test Module',
        })
        cls.enrollment = cls.env['siswa.kursus.enrollment'].with_user(
            cls.manager_user
        ).create({
            'siswa_id': cls.student.id,
            'modul_id': cls.learning_module.id,
        })

    def test_generic_internal_user_has_no_student_access(self):
        with self.assertRaises(AccessError):
            self.env['m.siswa'].with_user(
                self.internal_user
            ).check_access_rights('read')

    def test_viewer_is_read_only_and_cannot_read_password(self):
        student = self.student.with_user(self.viewer_user)
        self.assertEqual(student.name, 'Student Security Test')
        with self.assertRaises(AccessError):
            student.write({'notes': 'Forbidden'})
        with self.assertRaises(AccessError):
            student.read(['password'])

    def test_trainer_can_operate_assessment_but_not_master_student(self):
        with self.assertRaises(AccessError):
            self.env['m.siswa'].with_user(self.trainer_user).create({
                'name': 'Forbidden Student',
            })

        assessment = self.env[
            'siswa.kursus.penilaian.sertifikat'
        ].with_user(self.trainer_user).create({
            'enrollment_id': self.enrollment.id,
        })
        assessment.with_user(self.trainer_user).write({
            'catatan': 'Trainer operational note',
        })
        with self.assertRaises(AccessError):
            assessment.with_user(self.trainer_user).unlink()

    def test_manager_has_full_master_access(self):
        student = self.student.with_user(self.manager_user)
        student.write({'notes': 'Manager update'})
        self.assertEqual(student.notes, 'Manager update')
        self.assertEqual(student.read(['password'])[0]['password'], 'must-not-be-readable')
