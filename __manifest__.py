# -*- coding: utf-8 -*-
{
    'name': "Database Siswa",
    'summary': """
        Modul kustom untuk mengelola database siswa KodingYuk!,
        termasuk level, jenis kelas, dan data akademik.
    """,
    'author': "PT Koding Yuk Academy", # Anda bisa ganti dengan nama Anda
    'website': "https://kodingyuk.id", # Ganti jika perlu
    'category': 'Education',
    'version': '17.0.2.0.2',
    'depends': [
        'base',
        'mail',     # Untuk chatter (log & histori)
        'contacts', # Karena kita berelasi ke res.partner
        'hr',       # Karena kita berelasi ke hr.employee (pelatih/pembina rapot)
        'account',  # product.product dan account.move untuk penagihan otomatis
        'modul_pembelajaran', # Kurikulum, ujian, dan poin penilaian
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',

        # Wizard
        'wizard/exam_start_wizard_views.xml',

        # Data
        'data/rapot_rubrik_data.xml',

        # Root menu is referenced by feature views below.
        'views/student_root_menu.xml',

        # Report
        'report/rapot_paperformat.xml',
        'report/rapot_templates.xml',

        # Views
        'views/m_level_siswa_views.xml',
        'views/m_class_type_views.xml',
        'views/m_enrollment_views.xml',
        'views/m_penilaian_sertifikat_views.xml',
        'views/m_exam_siswa_views.xml',
        'views/m_siswa_views.xml',
        'views/hr_employee_views.xml',
        'views/automation_cron.xml',

        # Menus
        'views/student_menus.xml',

        # Butuh menu_student_config dari student_menus.xml, load setelahnya
        'views/rapot_rubrik_views.xml',
    ],
    'installable': True,
    'application': True, # Jadikan ini sebagai aplikasi (muncul di menu utama)
    'auto_install': False,
    'license': 'LGPL-3',
}
