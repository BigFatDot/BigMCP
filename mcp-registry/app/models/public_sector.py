"""
Public Sector domain whitelist for free Enterprise licenses.

Government, education, and healthcare organizations receive
free Enterprise licenses through the Public Sector Program.
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, Index
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, UUIDMixin, TimestampMixin


class PublicSectorCategory(str, enum.Enum):
    """Category of public sector organization."""
    GOVERNMENT = "government"
    LOCAL_AUTHORITY = "local_authority"
    EDUCATION = "education"
    HEALTHCARE = "healthcare"
    RESEARCH = "research"
    INTERNATIONAL = "international"


class PublicDomainWhitelist(Base, UUIDMixin, TimestampMixin):
    """
    Verified public sector domains eligible for free Enterprise licenses.

    When a user with an email from a whitelisted domain initiates
    Enterprise checkout, a 100% discount coupon is applied server-side.
    """

    __tablename__ = "public_domain_whitelist"

    # Domain (e.g., "gouv.fr", "paris.fr", "aphp.fr")
    domain: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True
    )

    # Organization details
    organization_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    country: Mapped[str] = mapped_column(
        String(2),
        nullable=False  # ISO 3166-1 alpha-2 code
    )
    category: Mapped[PublicSectorCategory] = mapped_column(
        SQLEnum(
            PublicSectorCategory,
            name="public_sector_category",
            values_callable=lambda x: [e.value for e in x]
        ),
        nullable=False,
        index=True
    )

    # Audit trail
    added_by: Mapped[str] = mapped_column(
        String(255),
        nullable=False  # Email of admin who added this entry
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False
    )

    # Indexes for efficient lookups
    __table_args__ = (
        Index("idx_whitelist_domain_active", domain, is_active),
        Index("idx_whitelist_country", country),
    )

    def __repr__(self) -> str:
        return (
            f"<PublicDomainWhitelist(domain={self.domain}, "
            f"org={self.organization_name}, country={self.country})>"
        )


# Initial seed data for the whitelist
INITIAL_WHITELIST = [
    # France - Central Government
    {
        "domain": "gouv.fr",
        "organization_name": "French Government",
        "country": "FR",
        "category": PublicSectorCategory.GOVERNMENT,
    },
    {
        "domain": "elysee.fr",
        "organization_name": "Presidency of the French Republic",
        "country": "FR",
        "category": PublicSectorCategory.GOVERNMENT,
    },
    {
        "domain": "assemblee-nationale.fr",
        "organization_name": "French National Assembly",
        "country": "FR",
        "category": PublicSectorCategory.GOVERNMENT,
    },
    {
        "domain": "senat.fr",
        "organization_name": "French Senate",
        "country": "FR",
        "category": PublicSectorCategory.GOVERNMENT,
    },

    # France - Major Cities
    {
        "domain": "paris.fr",
        "organization_name": "City of Paris",
        "country": "FR",
        "category": PublicSectorCategory.LOCAL_AUTHORITY,
    },
    {
        "domain": "lyon.fr",
        "organization_name": "City of Lyon",
        "country": "FR",
        "category": PublicSectorCategory.LOCAL_AUTHORITY,
    },
    {
        "domain": "marseille.fr",
        "organization_name": "City of Marseille",
        "country": "FR",
        "category": PublicSectorCategory.LOCAL_AUTHORITY,
    },
    {
        "domain": "toulouse.fr",
        "organization_name": "City of Toulouse",
        "country": "FR",
        "category": PublicSectorCategory.LOCAL_AUTHORITY,
    },
    {
        "domain": "nice.fr",
        "organization_name": "City of Nice",
        "country": "FR",
        "category": PublicSectorCategory.LOCAL_AUTHORITY,
    },
    {
        "domain": "nantes.fr",
        "organization_name": "City of Nantes",
        "country": "FR",
        "category": PublicSectorCategory.LOCAL_AUTHORITY,
    },
    {
        "domain": "strasbourg.eu",
        "organization_name": "City of Strasbourg",
        "country": "FR",
        "category": PublicSectorCategory.LOCAL_AUTHORITY,
    },
    {
        "domain": "bordeaux.fr",
        "organization_name": "City of Bordeaux",
        "country": "FR",
        "category": PublicSectorCategory.LOCAL_AUTHORITY,
    },
    {
        "domain": "lille.fr",
        "organization_name": "City of Lille",
        "country": "FR",
        "category": PublicSectorCategory.LOCAL_AUTHORITY,
    },
    {
        "domain": "rennes.fr",
        "organization_name": "City of Rennes",
        "country": "FR",
        "category": PublicSectorCategory.LOCAL_AUTHORITY,
    },

    # France - Healthcare
    {
        "domain": "aphp.fr",
        "organization_name": "Assistance Publique - Hopitaux de Paris",
        "country": "FR",
        "category": PublicSectorCategory.HEALTHCARE,
    },
    {
        "domain": "chu-lyon.fr",
        "organization_name": "Hospices Civils de Lyon",
        "country": "FR",
        "category": PublicSectorCategory.HEALTHCARE,
    },
    {
        "domain": "ap-hm.fr",
        "organization_name": "Assistance Publique - Hopitaux de Marseille",
        "country": "FR",
        "category": PublicSectorCategory.HEALTHCARE,
    },

    # France - Education
    {
        "domain": "education.fr",
        "organization_name": "French Ministry of Education",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-paris.fr",
        "organization_name": "Paris Academy",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },

    # France - Education (Académies - regional education authorities)
    {
        "domain": "ac-lyon.fr",
        "organization_name": "Académie de Lyon",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-aix-marseille.fr",
        "organization_name": "Académie d'Aix-Marseille",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-versailles.fr",
        "organization_name": "Académie de Versailles",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-creteil.fr",
        "organization_name": "Académie de Créteil",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-lille.fr",
        "organization_name": "Académie de Lille",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-toulouse.fr",
        "organization_name": "Académie de Toulouse",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-bordeaux.fr",
        "organization_name": "Académie de Bordeaux",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-nantes.fr",
        "organization_name": "Académie de Nantes",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-rennes.fr",
        "organization_name": "Académie de Rennes",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-strasbourg.fr",
        "organization_name": "Académie de Strasbourg",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-montpellier.fr",
        "organization_name": "Académie de Montpellier",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-grenoble.fr",
        "organization_name": "Académie de Grenoble",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-nancy-metz.fr",
        "organization_name": "Académie de Nancy-Metz",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-rouen.fr",
        "organization_name": "Académie de Normandie (Rouen)",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-dijon.fr",
        "organization_name": "Académie de Dijon",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-amiens.fr",
        "organization_name": "Académie d'Amiens",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-clermont.fr",
        "organization_name": "Académie de Clermont-Ferrand",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-poitiers.fr",
        "organization_name": "Académie de Poitiers",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-orleans-tours.fr",
        "organization_name": "Académie d'Orléans-Tours",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-besancon.fr",
        "organization_name": "Académie de Besançon",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-limoges.fr",
        "organization_name": "Académie de Limoges",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-reims.fr",
        "organization_name": "Académie de Reims",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-caen.fr",
        "organization_name": "Académie de Normandie (Caen)",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-corse.fr",
        "organization_name": "Académie de Corse",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-reunion.fr",
        "organization_name": "Académie de La Réunion",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-guadeloupe.fr",
        "organization_name": "Académie de Guadeloupe",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-martinique.fr",
        "organization_name": "Académie de Martinique",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-guyane.fr",
        "organization_name": "Académie de Guyane",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ac-mayotte.fr",
        "organization_name": "Académie de Mayotte",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },

    # France - Higher Education (Grandes écoles publiques)
    {
        "domain": "polytechnique.fr",
        "organization_name": "École Polytechnique",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ens.fr",
        "organization_name": "École Normale Supérieure (Paris)",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "ens-lyon.fr",
        "organization_name": "ENS de Lyon",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "enpc.fr",
        "organization_name": "École des Ponts ParisTech",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },
    {
        "domain": "centralesupelec.fr",
        "organization_name": "CentraleSupélec",
        "country": "FR",
        "category": PublicSectorCategory.EDUCATION,
    },

    # France - Research (EPST)
    {
        "domain": "cnrs.fr",
        "organization_name": "CNRS - Centre national de la recherche scientifique",
        "country": "FR",
        "category": PublicSectorCategory.RESEARCH,
    },
    {
        "domain": "inria.fr",
        "organization_name": "INRIA - Institut national de recherche en informatique",
        "country": "FR",
        "category": PublicSectorCategory.RESEARCH,
    },
    {
        "domain": "inserm.fr",
        "organization_name": "INSERM - Institut national de la santé et de la recherche médicale",
        "country": "FR",
        "category": PublicSectorCategory.RESEARCH,
    },
    {
        "domain": "inrae.fr",
        "organization_name": "INRAE - Institut national de recherche pour l'agriculture et l'environnement",
        "country": "FR",
        "category": PublicSectorCategory.RESEARCH,
    },
    {
        "domain": "ird.fr",
        "organization_name": "IRD - Institut de recherche pour le développement",
        "country": "FR",
        "category": PublicSectorCategory.RESEARCH,
    },

    # France - Research & Technical (EPIC - Établissements publics industriels et commerciaux)
    {
        "domain": "cerema.fr",
        "organization_name": "CEREMA - Centre d'études et d'expertise sur les risques, l'environnement, la mobilité et l'aménagement",
        "country": "FR",
        "category": PublicSectorCategory.RESEARCH,
    },
    {
        "domain": "ademe.fr",
        "organization_name": "ADEME - Agence de la transition écologique",
        "country": "FR",
        "category": PublicSectorCategory.RESEARCH,
    },
    {
        "domain": "brgm.fr",
        "organization_name": "BRGM - Bureau de recherches géologiques et minières",
        "country": "FR",
        "category": PublicSectorCategory.RESEARCH,
    },
    {
        "domain": "cea.fr",
        "organization_name": "CEA - Commissariat à l'énergie atomique et aux énergies alternatives",
        "country": "FR",
        "category": PublicSectorCategory.RESEARCH,
    },
    {
        "domain": "cnes.fr",
        "organization_name": "CNES - Centre national d'études spatiales",
        "country": "FR",
        "category": PublicSectorCategory.RESEARCH,
    },
    {
        "domain": "ifremer.fr",
        "organization_name": "IFREMER - Institut français de recherche pour l'exploitation de la mer",
        "country": "FR",
        "category": PublicSectorCategory.RESEARCH,
    },
    {
        "domain": "ign.fr",
        "organization_name": "IGN - Institut national de l'information géographique et forestière",
        "country": "FR",
        "category": PublicSectorCategory.RESEARCH,
    },
    {
        "domain": "ineris.fr",
        "organization_name": "INERIS - Institut national de l'environnement industriel et des risques",
        "country": "FR",
        "category": PublicSectorCategory.RESEARCH,
    },
    {
        "domain": "onera.fr",
        "organization_name": "ONERA - Office national d'études et de recherches aérospatiales",
        "country": "FR",
        "category": PublicSectorCategory.RESEARCH,
    },
    {
        "domain": "cirad.fr",
        "organization_name": "CIRAD - Centre de coopération internationale en recherche agronomique",
        "country": "FR",
        "category": PublicSectorCategory.RESEARCH,
    },
    {
        "domain": "cstb.fr",
        "organization_name": "CSTB - Centre scientifique et technique du bâtiment",
        "country": "FR",
        "category": PublicSectorCategory.RESEARCH,
    },
    {
        "domain": "ifpenergiesnouvelles.fr",
        "organization_name": "IFPEN - IFP Énergies nouvelles",
        "country": "FR",
        "category": PublicSectorCategory.RESEARCH,
    },
    {
        "domain": "irsn.fr",
        "organization_name": "IRSN - Institut de radioprotection et de sûreté nucléaire",
        "country": "FR",
        "category": PublicSectorCategory.RESEARCH,
    },
    {
        "domain": "anses.fr",
        "organization_name": "ANSES - Agence nationale de sécurité sanitaire",
        "country": "FR",
        "category": PublicSectorCategory.RESEARCH,
    },
    {
        "domain": "andra.fr",
        "organization_name": "ANDRA - Agence nationale pour la gestion des déchets radioactifs",
        "country": "FR",
        "category": PublicSectorCategory.RESEARCH,
    },
    {
        "domain": "meteofrance.fr",
        "organization_name": "Météo-France",
        "country": "FR",
        "category": PublicSectorCategory.RESEARCH,
    },

    # France - Government institutions with own domains
    {
        "domain": "banque-france.fr",
        "organization_name": "Banque de France",
        "country": "FR",
        "category": PublicSectorCategory.GOVERNMENT,
    },
    {
        "domain": "ccomptes.fr",
        "organization_name": "Cour des comptes",
        "country": "FR",
        "category": PublicSectorCategory.GOVERNMENT,
    },
    {
        "domain": "conseil-etat.fr",
        "organization_name": "Conseil d'État",
        "country": "FR",
        "category": PublicSectorCategory.GOVERNMENT,
    },
    {
        "domain": "conseil-constitutionnel.fr",
        "organization_name": "Conseil constitutionnel",
        "country": "FR",
        "category": PublicSectorCategory.GOVERNMENT,
    },

    # France - Healthcare (CHUs)
    {
        "domain": "chu-toulouse.fr",
        "organization_name": "CHU de Toulouse",
        "country": "FR",
        "category": PublicSectorCategory.HEALTHCARE,
    },
    {
        "domain": "chu-bordeaux.fr",
        "organization_name": "CHU de Bordeaux",
        "country": "FR",
        "category": PublicSectorCategory.HEALTHCARE,
    },
    {
        "domain": "chu-nantes.fr",
        "organization_name": "CHU de Nantes",
        "country": "FR",
        "category": PublicSectorCategory.HEALTHCARE,
    },
    {
        "domain": "chu-lille.fr",
        "organization_name": "CHU de Lille",
        "country": "FR",
        "category": PublicSectorCategory.HEALTHCARE,
    },
    {
        "domain": "chu-montpellier.fr",
        "organization_name": "CHU de Montpellier",
        "country": "FR",
        "category": PublicSectorCategory.HEALTHCARE,
    },
    {
        "domain": "chru-strasbourg.fr",
        "organization_name": "CHRU de Strasbourg",
        "country": "FR",
        "category": PublicSectorCategory.HEALTHCARE,
    },
    {
        "domain": "chu-rennes.fr",
        "organization_name": "CHU de Rennes",
        "country": "FR",
        "category": PublicSectorCategory.HEALTHCARE,
    },
    {
        "domain": "chu-grenoble.fr",
        "organization_name": "CHU Grenoble Alpes",
        "country": "FR",
        "category": PublicSectorCategory.HEALTHCARE,
    },
    {
        "domain": "chu-nice.fr",
        "organization_name": "CHU de Nice",
        "country": "FR",
        "category": PublicSectorCategory.HEALTHCARE,
    },

    # European Union
    {
        "domain": "europa.eu",
        "organization_name": "European Union",
        "country": "EU",
        "category": PublicSectorCategory.INTERNATIONAL,
    },
    {
        "domain": "europarl.europa.eu",
        "organization_name": "European Parliament",
        "country": "EU",
        "category": PublicSectorCategory.INTERNATIONAL,
    },

    # United Kingdom
    {
        "domain": "gov.uk",
        "organization_name": "UK Government",
        "country": "GB",
        "category": PublicSectorCategory.GOVERNMENT,
    },
    {
        "domain": "nhs.uk",
        "organization_name": "National Health Service",
        "country": "GB",
        "category": PublicSectorCategory.HEALTHCARE,
    },

    # Germany
    {
        "domain": "bund.de",
        "organization_name": "German Federal Government",
        "country": "DE",
        "category": PublicSectorCategory.GOVERNMENT,
    },

    # United States
    {
        "domain": "gov",
        "organization_name": "US Government",
        "country": "US",
        "category": PublicSectorCategory.GOVERNMENT,
    },
    {
        "domain": "edu",
        "organization_name": "US Educational Institutions",
        "country": "US",
        "category": PublicSectorCategory.EDUCATION,
    },

    # Canada
    {
        "domain": "gc.ca",
        "organization_name": "Government of Canada",
        "country": "CA",
        "category": PublicSectorCategory.GOVERNMENT,
    },

    # Switzerland
    {
        "domain": "admin.ch",
        "organization_name": "Swiss Federal Administration",
        "country": "CH",
        "category": PublicSectorCategory.GOVERNMENT,
    },

    # Belgium
    {
        "domain": "belgium.be",
        "organization_name": "Belgian Federal Government",
        "country": "BE",
        "category": PublicSectorCategory.GOVERNMENT,
    },
]
