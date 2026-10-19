# Clinique médicale

Module Odoo 19 pour un cabinet : patients, médecins, rendez-vous, ordonnances, laboratoire et demandes de radiographie.

Le dossier `medicalclinic` est un addon autonome. Il se copie dans le chemin des addons. Il ne contient pas le serveur Odoo, et il ne pilote pas les machines de radiologie.

## Fonctionnalités

### Patients

- Fiche : nom, sexe, date de naissance, âge calculé, téléphone, e-mail, groupe sanguin, antécédents.
- Numéro fixe du type `PAT00001`, unique, généré à la création. C'est ce numéro que l'on ressaisit sur le logiciel de radiologie pour rattacher une image.
- Onglet des radios du patient.
- Suivi des modifications dans le chatter.

### Médecins

- Fiche : nom, spécialité, téléphone, e-mail, tarif de consultation.
- Un compte Odoo peut être lié au médecin. Les règles d'accès s'en servent pour ne lui montrer que ses propres dossiers.

### Rendez-vous

- Référence automatique, patient, médecin, date.
- Statuts : brouillon, confirmé, terminé, annulé. Le passage d'un statut à l'autre est contrôlé.
- Motif, compte-rendu de consultation.
- Onglets ordonnances et radios du même rendez-vous.
- Vues liste, formulaire, kanban et calendrier.

### Prise de rendez-vous en ligne

La page `/prendre-rendez-vous` est le site public de la clinique. Elle n'affiche pas le menu Odoo.

La réception prépare les créneaux de la semaine pour un médecin, dans **Créneaux**, puis les lui envoie. Le médecin confirme l'heure, ou la modifie. Seuls les créneaux confirmés et encore libres apparaissent sur le site.

Le patient choisit d'abord le médecin, ensuite un jour disponible, ensuite une heure de ce jour. Odoo retrouve le patient s'il a déjà le même nom et le même téléphone, sinon il crée la fiche. Le rendez-vous est créé en brouillon sur ce créneau. La réception le voit dans la colonne Brouillon de `/clinic`. Si elle annule le rendez-vous, l'heure redevient disponible.

### Ordonnances

- Une ordonnance est liée au patient, au médecin et, si besoin, à la consultation.
- Chaque ligne est un médicament du catalogue : posologie, durée, quantité, précisions.
- Le catalogue porte le nom commercial, la DCI, le dosage, la forme (comprimé, gélule, sirop, injectable, etc.), la voie et la classe (antibiotique, antalgique, anti-inflammatoire, etc.).
- PDF de l'ordonnance, et envoi par e-mail au patient quand une adresse existe.

### Laboratoire

Le médecin coche un ou plusieurs bilans :

- NFS
- glycémie à jeun
- bilan lipidique
- bilan rénal
- bilan hépatique
- bilan hormonal
- bilan ionique

La demande passe de brouillon à « en cours », puis à « résultats prêts ». Le laboratoire saisit chaque paramètre. La valeur est comparée à l'intervalle de référence, avec un drapeau normal, haut ou bas. Les normes qui dépendent du sexe ou de l'âge, comme l'AMH, sont prises sur la fiche patient.

Un QR code et un jeton ouvrent la page publique des résultats, `/lab/results/<id>?access_token=...`. Sans le bon jeton, la page n'existe pas. Le médecin peut aussi produire le PDF et envoyer les résultats par e-mail.

### Radiographie

La demande décrit l'examen. Elle ne reçoit pas l'image DICOM et elle n'imprime pas le film.

- Région : genou, hanche, rachis, épaule, cheville, poignet, main, pied, bassin, coude, ou autre.
- Côté : gauche, droit, les deux, ou sans côté.
- Statuts : demandée, image reçue, compte-rendu validé.
- Le numéro patient est affiché pour être ressaisi sur le logiciel des machines.
- On colle le lien de l'image, puis **Image reçue**. **Ouvrir l'image** ouvre ce lien. Le médecin écrit le compte-rendu et le valide.
- L'adresse `POST /clinic/radiology/image` rattache une image déjà arrivée. Elle exige un utilisateur connecté du groupe médecin principal ou administrateur clinique, le numéro patient, et éventuellement le lien et l'identifiant DICOM. Elle cherche la demande encore au statut « demandée ».

L'impression et la lecture diagnostique restent sur le logiciel du constructeur.

### Espace web `/clinic`

Trois rôles travaillent sur un kanban, sans l'interface classique d'Odoo :

- **Réceptionniste** : patients et rendez-vous.
- **Médecin** : ses consultations, ses demandes d'analyses et ses ordonnances. Sa fiche médecin doit pointer vers son compte.
- **Laborantin** : saisie et validation des résultats.

Depuis cet espace : créer un patient, un rendez-vous ou une demande d'analyse, ouvrir la consultation, rédiger l'ordonnance, télécharger le PDF, envoyer l'e-mail, saisir le laboratoire.

### Droits

| Groupe | Où il travaille | Rôle |
| --- | --- | --- |
| Réceptionniste | `/clinic` | Patients et rendez-vous |
| Laborantin | `/clinic` | Résultats des demandes déjà envoyées |
| Médecin | `/clinic` | Ses rendez-vous, ses analyses, ses ordonnances, ses radios |
| Médecin principal | Interface Odoo | Tout le cabinet, y compris les radios |
| Administrateur clinique | Interface Odoo | Le médecin principal, plus les médecins et le catalogue de médicaments |

Un médecin ne voit que les dossiers dont la fiche médecin est liée à son compte. L'administrateur et le médecin principal n'ont pas cette limite.

### PDF

- Ordonnance
- Compte-rendu de laboratoire

## Installation

1. Copier ce dossier dans le chemin des addons, par exemple `odoo/custom_addons/medicalclinic`.
2. Le QR code du laboratoire utilise la librairie `qrcode` : `pip install qrcode`.
3. Démarrer Odoo avec ce chemin dans `addons_path`.
4. Activer le mode développeur, mettre à jour la liste des applications, puis installer **Gestion de Clinique Médicale**.

Dépendances Odoo : `base`, `mail`, `web`.

```bash
odoo-bin -c odoo.conf -d NOM_BASE -i medicalclinic
```

Après une mise à jour du code :

```bash
odoo-bin -c odoo.conf -d NOM_BASE -u medicalclinic --stop-after-init
```

## Tests

Les tests sont dans `tests/test_clinic.py`. Ils couvrent le passage des rendez-vous, le tableau de créneaux de la semaine, la confirmation du médecin, la réservation en ligne, l'ordonnance, le drapeau du laboratoire et le rattachement d'une radio.

```bash
odoo-bin -c odoo.conf -d NOM_BASE -u medicalclinic --test-enable --test-tags /medicalclinic --stop-after-init
```

## Technique

- Version du module : `1.6.0`
- Licence : LGPL-3
- Modèles : `clinic.patient`, `clinic.doctor`, `clinic.appointment`, `clinic.prescription`, `clinic.prescription.line`, `clinic.medication`, `clinic.lab.request`, `clinic.lab.result.line`, `clinic.radiology.request`

---

## English

Odoo 19 addon for a doctor's office: patients, doctors, appointments, prescriptions, laboratory, and X-ray requests.

The `medicalclinic` folder is a standalone addon. Copy it into the addons path. It does not include the Odoo server, and it does not drive radiology machines.

### Features

#### Patients

- Record: name, sex, date of birth, computed age, phone, email, blood group, medical history.
- A fixed number such as `PAT00001`, unique, set on creation. That number is typed again in the radiology software so an image can be matched to the record.
- A tab lists the patient's X-ray requests.
- Changes are tracked on the chatter.

#### Doctors

- Record: name, specialty, phone, email, consultation fee.
- An Odoo user can be linked to the doctor. Access rules then show that doctor only their own files.

#### Appointments

- Automatic reference, patient, doctor, date.
- States: draft, confirmed, done, cancelled. Transitions are checked.
- Reason for the visit, and consultation notes.
- Tabs for the prescriptions and X-ray requests of the same appointment.
- List, form, kanban, and calendar views.

#### Online booking

`/prendre-rendez-vous` is the public clinic page. It does not show the Odoo menu.

Reception prepares the week's slots for a doctor under **Créneaux**, then sends them. The doctor confirms the time, or changes it. Only confirmed free slots appear on the site.

The patient first picks the doctor, then an open day, then an hour of that day. Odoo reuses the patient when the same name and phone already exist, otherwise it creates the record. The appointment is created as a draft on that slot. Reception sees it in the Draft column of `/clinic`. Cancelling the appointment makes the hour available again.

#### Prescriptions

- A prescription is linked to the patient, the doctor, and optionally the consultation.
- Each line is a drug from the catalog: dosage, duration, quantity, extra instructions.
- The catalog stores the brand name, INN, strength, form (tablet, capsule, syrup, injection, and others), route, and class (antibiotic, analgesic, anti-inflammatory, and others).
- PDF prescription, and an email to the patient when an address exists.

#### Laboratory

The doctor ticks one or more panels:

- complete blood count
- fasting glucose
- lipid panel
- renal panel
- liver panel
- hormone panel
- electrolyte panel

The request moves from draft to in progress, then to results ready. The lab enters each analyte. The value is compared with the reference range and flagged normal, high, or low. Ranges that depend on sex or age, such as AMH, use the patient record.

A QR code and a token open the public results page, `/lab/results/<id>?access_token=...`. The wrong token returns a not-found page. The doctor can also print the PDF and email the results.

#### X-ray

The request describes the exam. It does not store the DICOM image and it does not print the film.

- Region: knee, hip, spine, shoulder, ankle, wrist, hand, foot, pelvis, elbow, or other.
- Side: left, right, both, or not applicable.
- States: requested, image received, report signed.
- The patient number is shown so it can be typed into the machine software.
- Paste the image link, then mark **Image received**. **Open the image** follows that link. The doctor writes the report and signs it.
- `POST /clinic/radiology/image` attaches an image that has already arrived. It requires a logged-in principal doctor or clinic administrator, the patient number, and optionally the link and the DICOM id. It looks up the request that is still in the requested state.

Diagnostic reading and film printing stay on the vendor software.

#### Web desk `/clinic`

Three roles work on a kanban board, outside the standard Odoo interface:

- **Receptionist**: patients and appointments.
- **Doctor**: own consultations, lab requests, and prescriptions. The doctor record must point to that user.
- **Lab technician**: enter and validate results.

From this desk: create a patient, an appointment, or a lab request, open the consultation, write the prescription, download the PDF, send the email, and fill in lab results.

#### Access

| Group | Where they work | Role |
| --- | --- | --- |
| Receptionist | `/clinic` | Patients and appointments |
| Lab technician | `/clinic` | Results of requests already sent |
| Doctor | `/clinic` | Own appointments, lab requests, prescriptions, and X-rays |
| Principal doctor | Odoo interface | The whole office, including X-rays |
| Clinic administrator | Odoo interface | The principal doctor, plus doctors and the drug catalog |

A doctor only sees files whose doctor record is linked to their user. The administrator and the principal doctor do not have that limit.

#### PDF

- Prescription
- Laboratory report

### Installation

1. Copy this folder into the addons path, for example `odoo/custom_addons/medicalclinic`.
2. The lab QR code uses the `qrcode` library: `pip install qrcode`.
3. Start Odoo with that path in `addons_path`.
4. Enable developer mode, update the apps list, then install **Gestion de Clinique Médicale**.

Odoo dependencies: `base`, `mail`, `web`.

```bash
odoo-bin -c odoo.conf -d DATABASE -i medicalclinic
```

After a code update:

```bash
odoo-bin -c odoo.conf -d DATABASE -u medicalclinic --stop-after-init
```

### Tests

`tests/test_clinic.py` covers appointment transitions, the weekly slot grid, doctor confirmation, online booking, prescriptions, the laboratory flag, and attaching an X-ray link.

```bash
odoo-bin -c odoo.conf -d DATABASE -u medicalclinic --test-enable --test-tags /medicalclinic --stop-after-init
```

### Technical

- Module version: `1.6.0`
- License: LGPL-3
- Models: `clinic.patient`, `clinic.doctor`, `clinic.appointment`, `clinic.prescription`, `clinic.prescription.line`, `clinic.medication`, `clinic.lab.request`, `clinic.lab.result.line`, `clinic.radiology.request`

---

## Deutsch

Odoo-19-Modul für eine Arztpraxis: Patienten, Ärzte, Termine, Rezepte, Labor und Röntgenanforderungen.

Der Ordner `medicalclinic` ist ein eigenständiges Addon. Er wird in den Addons-Pfad kopiert. Er enthält nicht den Odoo-Server und steuert keine Röntgengeräte.

### Funktionen

#### Patienten

- Karte: Name, Geschlecht, Geburtsdatum, berechnetes Alter, Telefon, E-Mail, Blutgruppe, Vorgeschichte.
- Eine feste Nummer wie `PAT00001`, eindeutig, bei der Anlage gesetzt. Dieselbe Nummer wird in der Radiologiesoftware erfasst, damit ein Bild zur Karte passt.
- Ein Reiter listet die Röntgenanforderungen des Patienten.
- Änderungen stehen im Chatter.

#### Ärzte

- Karte: Name, Fachgebiet, Telefon, E-Mail, Konsultationshonorar.
- Ein Odoo-Benutzer kann mit dem Arzt verknüpft werden. Zugriffsregeln zeigen ihm dann nur die eigenen Akten.

#### Termine

- Automatische Referenz, Patient, Arzt, Datum.
- Status: Entwurf, bestätigt, erledigt, abgesagt. Die Übergänge werden geprüft.
- Anlass und Konsultationsbericht.
- Reiter für Rezepte und Röntgenanforderungen desselben Termins.
- Listen-, Formular-, Kanban- und Kalenderansicht.

#### Online-Termin

`/prendre-rendez-vous` ist die öffentliche Praxisseite. Das Odoo-Menü erscheint dort nicht.

Der Empfang bereitet die Wochentermine eines Arztes unter **Créneaux** vor und sendet sie. Der Arzt bestätigt die Uhrzeit oder ändert sie. Nur bestätigte freie Termine erscheinen auf der Seite.

Der Patient wählt zuerst den Arzt, dann einen offenen Tag, dann eine Uhrzeit dieses Tages. Odoo verwendet den Patienten wieder, wenn Name und Telefon schon existieren, sonst legt es die Karte an. Der Termin entsteht als Entwurf auf diesem Termin. Der Empfang sieht ihn in der Spalte Entwurf von `/clinic`. Eine Absage gibt die Uhrzeit wieder frei.

#### Rezepte

- Ein Rezept hängt am Patienten, am Arzt und bei Bedarf an der Konsultation.
- Jede Zeile ist ein Medikament aus dem Katalog: Dosierung, Dauer, Menge, Hinweise.
- Der Katalog speichert Handelsname, INN, Stärke, Form (Tablette, Kapsel, Sirup, Injektion und weitere), Weg und Klasse (Antibiotikum, Analgetikum, Antiphlogistikum und weitere).
- PDF-Rezept, und eine E-Mail an den Patienten, wenn eine Adresse vorhanden ist.

#### Labor

Der Arzt kreuzt ein oder mehrere Profile an:

- Blutbild
- Nüchternglukose
- Lipidprofil
- Nierenprofil
- Leberprofil
- Hormonprofil
- Elektrolyte

Die Anforderung geht von Entwurf zu „in Arbeit“, dann zu „Ergebnisse fertig“. Das Labor erfasst jeden Parameter. Der Wert wird mit dem Referenzbereich verglichen und als normal, hoch oder niedrig markiert. Bereiche, die von Geschlecht oder Alter abhängen, etwa AMH, nutzen die Patientenkarte.

Ein QR-Code und ein Token öffnen die öffentliche Ergebnisseite `/lab/results/<id>?access_token=...`. Ein falsches Token liefert eine Nicht-gefunden-Seite. Der Arzt kann auch das PDF drucken und die Ergebnisse per E-Mail senden.

#### Röntgen

Die Anforderung beschreibt die Untersuchung. Sie speichert das DICOM-Bild nicht und druckt den Film nicht.

- Region: Knie, Hüfte, Wirbelsäule, Schulter, Sprunggelenk, Handgelenk, Hand, Fuß, Becken, Ellenbogen oder andere.
- Seite: links, rechts, beide oder keine Seite.
- Status: angefordert, Bild eingetroffen, Bericht freigegeben.
- Die Patientennummer wird angezeigt, damit sie in der Gerätesoftware erfasst werden kann.
- Den Bildlink einfügen, dann **Bild eingetroffen**. **Bild öffnen** folgt diesem Link. Der Arzt schreibt den Bericht und gibt ihn frei.
- `POST /clinic/radiology/image` hängt ein bereits eingetroffenes Bild an. Nötig sind ein angemeldeter leitender Arzt oder Klinikadministrator, die Patientennummer und optional Link und DICOM-Kennung. Gesucht wird die Anforderung, die noch auf „angefordert“ steht.

Befundung und Filmausdruck bleiben in der Herstellersoftware.

#### Web-Schalter `/clinic`

Drei Rollen arbeiten auf einem Kanban, außerhalb der klassischen Odoo-Oberfläche:

- **Empfang**: Patienten und Termine.
- **Arzt**: eigene Konsultationen, Laboranforderungen und Rezepte. Die Arztkarte muss auf dieses Benutzerkonto zeigen.
- **Labor**: Ergebnisse erfassen und freigeben.

Von dort: Patient, Termin oder Laboranforderung anlegen, die Konsultation öffnen, das Rezept schreiben, das PDF laden, die E-Mail senden und Laborwerte eintragen.

#### Rechte

| Gruppe | Arbeitsplatz | Rolle |
| --- | --- | --- |
| Empfang | `/clinic` | Patienten und Termine |
| Labor | `/clinic` | Ergebnisse bereits gesendeter Anforderungen |
| Arzt | `/clinic` | Eigene Termine, Labor, Rezepte und Röntgen |
| Leitender Arzt | Odoo-Oberfläche | Die ganze Praxis, einschließlich Röntgen |
| Klinikadministration | Odoo-Oberfläche | Der leitende Arzt, plus Ärzte und Medikamentenkatalog |

Ein Arzt sieht nur Akten, deren Arztkarte mit seinem Benutzer verknüpft ist. Administration und leitender Arzt haben diese Grenze nicht.

#### PDF

- Rezept
- Laborbericht

### Installation

1. Diesen Ordner in den Addons-Pfad kopieren, zum Beispiel `odoo/custom_addons/medicalclinic`.
2. Der Labor-QR-Code nutzt die Bibliothek `qrcode`: `pip install qrcode`.
3. Odoo mit diesem Pfad in `addons_path` starten.
4. Entwicklermodus einschalten, die Anwendungsliste aktualisieren, dann **Gestion de Clinique Médicale** installieren.

Odoo-Abhängigkeiten: `base`, `mail`, `web`.

```bash
odoo-bin -c odoo.conf -d DATENBANK -i medicalclinic
```

Nach einer Codeänderung:

```bash
odoo-bin -c odoo.conf -d DATENBANK -u medicalclinic --stop-after-init
```

### Tests

`tests/test_clinic.py` prüft die Terminstatus, die Wochentabelle, die Bestätigung durch den Arzt, die Online-Buchung, das Rezept, die Labormarkierung und das Anhängen eines Röntgenlinks.

```bash
odoo-bin -c odoo.conf -d DATENBANK -u medicalclinic --test-enable --test-tags /medicalclinic --stop-after-init
```

### Technik

- Modulversion: `1.6.0`
- Lizenz: LGPL-3
- Modelle: `clinic.patient`, `clinic.doctor`, `clinic.appointment`, `clinic.prescription`, `clinic.prescription.line`, `clinic.medication`, `clinic.lab.request`, `clinic.lab.result.line`, `clinic.radiology.request`

---

<div dir="rtl">

## العربية

تطبيق أودو 19 لعيادة: المرضى، والأطباء، والمواعيد، والوصفات، والمختبر، وطلبات الأشعة.

مجلد `medicalclinic` إضافة مستقلة. يُنسخ إلى مسار الإضافات. لا يتضمّن خادم أودو، ولا يتحكّم في أجهزة الأشعة.

### الوظائف

#### المرضى

- البطاقة: الاسم، والجنس، وتاريخ الميلاد، والسن المحسوب، والهاتف، والبريد، وفصيلة الدم، والسوابق.
- رقم ثابت مثل `PAT00001`، فريد، يُنشأ عند إنشاء البطاقة. يُعاد إدخال هذا الرقم في برنامج الأشعة لربط الصورة بالبطاقة.
- لسان يعرض طلبات أشعة المريض.
- التعديلات تُتابع في المحادثة.

#### الأطباء

- البطاقة: الاسم، والتخصص، والهاتف، والبريد، وثمن الكشف.
- يمكن ربط حساب أودو بالطبيب. قواعد الوصول تعرض له ملفاته فقط.

#### المواعيد

- مرجع تلقائي، ومريض، وطبيب، وتاريخ.
- الحالات: مسودة، مؤكَّد، منتهٍ، ملغى. الانتقال بين الحالات مراقب.
- سبب الزيارة، وتقرير الكشف.
- ألسنة لوصفات وأشعة الموعد نفسه.
- عرض قائمة ونموذج وكانبان ورزنامة.

#### حجز عبر الموقع

`/prendre-rendez-vous` هي صفحة العيادة العامة. قائمة أودو لا تظهر فيها.

يُعدّ الاستقبال مواعيد الأسبوع لطبيب من **Créneaux** ثم يرسلها. يؤكد الطبيب الساعة أو يعدّلها. لا تظهر في الموقع إلا المواعيد المؤكدة والشاغرة.

يختار المريض أولاً الطبيب، ثم يوماً متاحاً، ثم ساعة ذلك اليوم. يعيد أودو استعمال المريض إذا وُجد نفس الاسم ونفس الهاتف، وإلا ينشئ البطاقة. يُنشأ الموعد كمسودة على هذا الموعد. يراه الاستقبال في عمود المسودة في `/clinic`. إلغاء الموعد يعيد الساعة إلى المتاح.

#### الوصفات

- الوصفة مرتبطة بالمريض والطبيب وعند الحاجة بالكشف.
- كل سطر دواء من الفهرس: الجرعة، والمدة، والكمية، وملاحظات.
- الفهرس يحفظ الاسم التجاري، والتسمية المشتركة، والعيار، والشكل (قرص، كبسولة، شراب، حقن وغيرها)، وطريقة الإعطاء، والفئة (مضاد حيوي، مسكّن، مضاد التهاب وغيرها).
- الوصفة PDF، ورسالة إلى المريض إذا وُجد بريد.

#### المختبر

يحدد الطبيب تحليلاً أو أكثر:

- تعداد الدم
- سكر الصيام
- الدهون
- وظائف الكلى
- وظائف الكبد
- الهرمونات
- الشوارد

ينتقل الطلب من مسودة إلى «قيد الإنجاز»، ثم إلى «النتائج جاهزة». المختبر يدخل كل مؤشر. تُقارن القيمة بالمجال المرجعي وتُعلَّم: طبيعي، أو مرتفع، أو منخفض. المجالات التي تعتمد على الجنس أو السن، مثل AMH، تُؤخذ من بطاقة المريض.

رمز QR ورمز سرّي يفتحان صفحة النتائج العامة `/lab/results/<id>?access_token=...`. الرمز الخاطئ يعيد صفحة غير موجودة. يستطيع الطبيب أيضاً إصدار PDF وإرسال النتائج بالبريد.

#### الأشعة

الطلب يصف الفحص. لا يخزّن صورة DICOM ولا يطبع الفيلم.

- المنطقة: ركبة، ورك، عمود فقري، كتف، كاحل، رسغ، يد، قدم، حوض، مرفق، أو غيرها.
- الجهة: يسرى، يمنى، الاثنتان، أو بلا جهة.
- الحالات: مطلوب، وصلت الصورة، اعتُمد التقرير.
- رقم المريض ظاهر ليُعاد إدخاله في برنامج الأجهزة.
- يُلصق رابط الصورة، ثم **وصلت الصورة**. **فتح الصورة** يتبع هذا الرابط. يكتب الطبيب التقرير ويعتمده.
- `POST /clinic/radiology/image` يربط صورة وصلت مسبقاً. يلزم مستخدم متصل من مجموعة الطبيب الرئيس أو مدير العيادة، ورقم المريض، واختيارياً الرابط ومعرّف DICOM. يُبحث عن الطلب الذي ما زال في حالة «مطلوب».

قراءة التشخيص وطباعة الفيلم تبقيان في برنامج الشركة المصنّعة.

#### مكتب الويب `/clinic`

ثلاثة أدوار تعمل على كانبان، خارج واجهة أودو المعتادة:

- **الاستقبال**: المرضى والمواعيد.
- **الطبيب**: كشوفاته وطلبات مختبره ووصفاته. يجب أن تشير بطاقة الطبيب إلى حسابه.
- **المختبر**: إدخال النتائج واعتمادها.

من هناك: إنشاء مريض أو موعد أو طلب تحليل، وفتح الكشف، وكتابة الوصفة، وتنزيل PDF، وإرسال البريد، وإدخال نتائج المختبر.

#### الصلاحيات

| المجموعة | مكان العمل | الدور |
| --- | --- | --- |
| الاستقبال | `/clinic` | المرضى والمواعيد |
| المختبر | `/clinic` | نتائج الطلبات المرسلة |
| الطبيب | `/clinic` | مواعيده ومختبره ووصفاته وأشعته |
| الطبيب الرئيس | واجهة أودو | كل العيادة، بما فيها الأشعة |
| مدير العيادة | واجهة أودو | الطبيب الرئيس، إضافة إلى الأطباء وفهرس الأدوية |

الطبيب يرى الملفات التي ترتبط بطاقة طبيبها بحسابه فقط. المدير والطبيب الرئيس بلا هذا الحد.

#### PDF

- الوصفة
- تقرير المختبر

### التثبيت

1. انسخ هذا المجلد إلى مسار الإضافات، مثلاً `odoo/custom_addons/medicalclinic`.
2. رمز QR في المختبر يستعمل مكتبة `qrcode`: `pip install qrcode`.
3. شغّل أودو مع هذا المسار في `addons_path`.
4. فعّل وضع المطوّر، حدّث قائمة التطبيقات، ثم ثبّت **Gestion de Clinique Médicale**.

اعتمادات أودو: `base` و`mail` و`web`.

```bash
odoo-bin -c odoo.conf -d DATABASE -i medicalclinic
```

بعد تعديل في الكود:

```bash
odoo-bin -c odoo.conf -d DATABASE -u medicalclinic --stop-after-init
```

### الاختبارات

يغطي `tests/test_clinic.py` انتقال المواعيد، وجدول الأسبوع، وتأكيد الطبيب، والحجز عبر الموقع، والوصفة، وعلامة المختبر، وربط صورة الأشعة.

```bash
odoo-bin -c odoo.conf -d DATABASE -u medicalclinic --test-enable --test-tags /medicalclinic --stop-after-init
```

### تقني

- إصدار الوحدة: `1.6.0`
- الرخصة: LGPL-3
- النماذج: `clinic.patient`, `clinic.doctor`, `clinic.appointment`, `clinic.prescription`, `clinic.prescription.line`, `clinic.medication`, `clinic.lab.request`, `clinic.lab.result.line`, `clinic.radiology.request`

</div>
