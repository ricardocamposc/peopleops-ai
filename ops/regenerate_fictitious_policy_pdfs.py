"""Regenerate the fictitious-company policy corpus as four-page PDFs.

The corpus is synthetic and intentionally contains distinct policy language so
retrieval quality can be measured without relying on filenames alone.
"""

from __future__ import annotations

import argparse
import json
import unicodedata
from datetime import UTC, datetime
from pathlib import Path


CONTENT: dict[str, tuple[str, ...]] = {
    "hr-manual": (
        "El manual define los principios generales para administrar la relación laboral y orientar a colaboradores y líderes.",
        "Las personas colaboradoras deben conocer las políticas aplicables, mantener sus datos actualizados y comunicar incidencias por los canales establecidos.",
        "Los líderes deben aplicar criterios consistentes, documentar decisiones y escalar situaciones que requieran interpretación legal o de People.",
        "People mantiene los registros corporativos, coordina revisiones y comunica cambios relevantes del marco de gestión de personas.",
        "El manual no sustituye contratos, legislación laboral ni procedimientos locales.",
    ),
    "recruitment-selection-policy": (
        "La política establece un proceso ordenado, objetivo y trazable para cubrir posiciones y seleccionar personas adecuadas.",
        "Toda vacante requiere una solicitud aprobada, una descripción del puesto, responsabilidades, requisitos y rango de compensación cuando corresponda.",
        "La selección puede incluir revisión curricular, entrevistas, evaluaciones y referencias según el puesto.",
        "Los criterios deben ser pertinentes y aplicarse de forma consistente; se prohíbe discriminar por motivos ajenos a los requisitos legítimos.",
        "People conserva la evidencia del proceso respetando privacidad y retención.",
    ),
    "onboarding-policy": (
        "El objetivo es asegurar que toda persona que ingresa reciba información, documentación, accesos, herramientas y acompañamiento para comenzar sus funciones.",
        "Antes del ingreso se coordinan contrato, beneficios, equipo, accesos y agenda con las áreas responsables.",
        "El primer día incluye bienvenida, políticas esenciales, responsable directo y canales de soporte.",
        "Durante la primera semana se revisan puesto, objetivos, herramientas y procesos; entre los días 30 y 90 se realizan seguimientos.",
        "People conserva el checklist y la constancia de entrega o aceptación de políticas.",
    ),
    "working-hours-attendance-policy": (
        "La política establece criterios para jornada, asistencia, puntualidad, ausencias y horas adicionales.",
        "Cada puesto tiene una jornada y modalidad definidas conforme al contrato y las reglas aplicables.",
        "Cuando existe control horario, la persona debe registrar su asistencia verazmente y comunicar incidencias oportunamente.",
        "Las horas extras o trabajos fuera de jornada requieren autorización previa cuando lo exijan la normativa o las reglas internas.",
        "En modalidad remota se mantienen las obligaciones de disponibilidad, seguridad, cumplimiento de jornada y resultados.",
    ),
    "vacation-policy": (
        "La política regula la planificación, solicitud, aprobación y registro de vacaciones para asegurar descanso y continuidad operativa.",
        "La persona colaboradora solicita vacaciones por el canal definido con la anticipación establecida y verifica su saldo disponible.",
        "El líder evalúa continuidad operativa, necesidades del equipo y reglas de prioridad antes de aprobar.",
        "People mantiene saldos y períodos utilizados, y valida registros cuando corresponde.",
        "Los cambios y cancelaciones deben acordarse y registrarse; una solicitud no equivale a aprobación.",
    ),
    "compensation-benefits-policy": (
        "La política establece principios para administrar salarios, beneficios, incentivos y revisiones de compensación.",
        "La compensación considera responsabilidades, experiencia, competencias, desempeño, mercado, presupuesto y equidad interna.",
        "Las revisiones salariales siguen ciclos definidos y no constituyen aumentos automáticos; requieren aprobaciones.",
        "Los incentivos tienen criterios de elegibilidad y condiciones de pago comunicadas previamente.",
        "La información individual de compensación es confidencial y de acceso restringido.",
    ),
    "performance-development-policy": (
        "La política conecta objetivos, seguimiento, feedback y desarrollo individual con las prioridades de la empresa.",
        "Los objetivos deben ser claros, medibles cuando sea posible, alcanzables y alineados con el área.",
        "Los líderes realizan conversaciones periódicas y proporcionan feedback oportuno, específico y respetuoso.",
        "Cuando el desempeño no alcanza expectativas puede establecerse un plan con brechas, acciones, responsables y plazos.",
        "Las iniciativas de desarrollo pueden incluir capacitación, mentoring, proyectos y movilidad interna.",
    ),
    "conduct-ethics-policy": (
        "La política define estándares de conducta, integridad, respeto y no discriminación para las relaciones laborales.",
        "Las decisiones deben basarse en criterios legítimos, documentarse cuando corresponda y evitar conflictos de interés.",
        "La empresa no tolera acoso, represalias, discriminación ni uso indebido de información corporativa.",
        "Las consultas o reportes deben comunicarse por los canales habilitados y tratarse con confidencialidad.",
        "People coordina orientación, registro y seguimiento de incidentes según su naturaleza.",
    ),
    "harassment-prevention-policy": (
        "La política busca prevenir acoso, violencia y conductas de hostigamiento en el trabajo.",
        "Toda persona debe mantener un trato respetuoso y puede reportar conductas preocupantes sin temor a represalias.",
        "People recibe reportes, protege la confidencialidad y coordina una revisión imparcial de los hechos.",
        "Las medidas se determinan considerando evidencia, gravedad, contexto y normativa aplicable.",
        "Los reportes de buena fe no generan consecuencias adversas por el solo hecho de ser presentados.",
    ),
    "information-privacy-policy": (
        "La política protege la confidencialidad, integridad y uso adecuado de la información personal de colaboradores.",
        "People recopila y utiliza datos solo para fines laborales legítimos, administración de personas, cumplimiento y seguridad.",
        "El acceso se limita a roles autorizados y debe utilizarse según la necesidad de conocer.",
        "Las personas deben proteger credenciales, evitar compartir información sensible y reportar incidentes.",
        "La conservación, eliminación y transferencia de datos siguen las reglas internas y la normativa aplicable.",
    ),
    "disciplinary-policy": (
        "La política establece un marco consistente para gestionar incumplimientos de obligaciones, políticas o normas de conducta.",
        "Las medidas deben ser proporcionales, consistentes, documentadas y respetuosas de la normativa aplicable.",
        "Antes de adoptar una medida se evalúan hechos, evidencia y circunstancias relevantes.",
        "Las decisiones graves requieren revisión de People o asesoría legal cuando corresponda.",
        "Los registros disciplinarios tienen acceso restringido y se conservan conforme a las reglas de privacidad.",
    ),
    "offboarding-policy": (
        "La política asegura una salida ordenada y segura, preservando derechos, continuidad operativa e información corporativa.",
        "People coordina documentación, pagos, beneficios y obligaciones pendientes conforme al contrato y la legislación.",
        "La persona debe devolver equipos, credenciales, documentos y activos que correspondan.",
        "Los accesos a sistemas, aplicaciones, correo y recursos deben modificarse o revocarse oportunamente.",
        "Cuando sea necesario se transfiere conocimiento y se documentan tareas para reducir el impacto operativo.",
    ),
}


def _ascii(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()


def _escape(value: str) -> str:
    return _ascii(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _render(path: Path, metadata: dict, paragraphs: tuple[str, ...]) -> None:
    objects: list[bytes] = []

    def add(value: bytes) -> int:
        objects.append(value)
        return len(objects)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids: list[int] = []
    sections = (
        ("1. Purpose and scope", paragraphs[:2]),
        ("2. Operating rules", paragraphs[2:4]),
        ("3. Responsibilities and evidence", paragraphs[4:]),
        ("4. Governance and related controls", (
            "The policy is reviewed annually or after a material organizational or regulatory change.",
            "People maintains the controlled version. Previous versions remain historical and are not an operational source.",
            "Questions outside this policy must be answered from the applicable controlled source and must not be inferred.",
        )),
    )
    for page_number, (section, items) in enumerate(sections, start=1):
        lines = [
            metadata["titulo"],
            f"Document key: {metadata['clave_documento']}",
            f"Version: {metadata['version']}",
            f"Effective from: {metadata['vigente_desde']}",
            f"Department: {metadata['departamento']}",
            f"Confidentiality: {metadata['confidencialidad']}",
            "Synthetic: true",
            "",
            section,
            "",
            *items,
            "",
            f"Controlled synthetic document - Page {page_number} of 4",
        ]
        commands = ["BT", "/F1 17 Tf", "48 748 Td", f"({_escape(lines[0])}) Tj", "/F1 9 Tf"]
        for line in lines[1:]:
            commands.extend(["0 -18 Td", f"({_escape(line)}) Tj"])
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1")
        content = add(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
        page_ids.append(add(
            f"<< /Type /Page /Parent PAGES /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font} 0 R >> >> /Contents {content} 0 R >>".encode()
        ))
    pages = add((f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count 4 >>").encode())
    catalog = add(f"<< /Type /Catalog /Pages {pages} 0 R >>".encode())
    info = add(f"<< /Title ({_escape(metadata['titulo'])}) /Author (PeopleOps AI Synthetic Corpus) /Subject (Synthetic policy for Policy RAG evaluation) /Keywords (synthetic, policy, {metadata['clave_documento']}) >>".encode())
    objects = [obj.replace(b"PAGES", f"{pages} 0 R".encode()) for obj in objects]
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, value in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n".encode())
        output.extend(value)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    output.extend("".join(f"{offset:010d} 00000 n \n" for offset in offsets[1:]).encode())
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R /Info {info} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.write_bytes(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, default=Path("policies/fictitious-company"))
    args = parser.parse_args()
    metadata_path = args.corpus_dir / "metadata_politicas_rrhh.json"
    records = json.loads(metadata_path.read_text(encoding="utf-8"))
    manifest = {"generated_at": datetime.now(UTC).isoformat(), "synthetic": True, "documents": []}
    for record in records:
        key = record["clave_documento"]
        if key not in CONTENT:
            raise RuntimeError(f"Missing synthetic content for {key}")
        destination = args.corpus_dir / f"{key}.pdf"
        _render(destination, record, CONTENT[key])
        manifest["documents"].append(
            {"document_key": key, "title": record["titulo"], "version": record["version"],
             "effective_from": datetime.strptime(record["vigente_desde"], "%d/%m/%Y").date().isoformat(),
             "department": record["departamento"], "confidentiality": record["confidencialidad"],
             "filename": str(destination), "pages": 4, "synthetic": True}
        )
    (args.corpus_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Generated {len(records)} four-page policy PDFs in {args.corpus_dir}")


if __name__ == "__main__":
    main()
