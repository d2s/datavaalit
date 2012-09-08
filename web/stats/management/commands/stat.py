import os

from django.core.management.base import BaseCommand
from stats.models import *
from utils.http import HttpFetcher
from django.conf import settings
from django.contrib.gis.gdal import DataSource, SpatialReference, CoordTransform
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon


MUNI_URL = "http://tilastokeskus.fi/meta/luokitukset/kunta/001-2012/tekstitiedosto.txt"
# http://latuviitta.org/documents/YKJ-TM35FIN_muunnos_ogr2ogr_cs2cs.txt

"""
def import_election_district_boundaries(self, data_path):
    path = os.path.join(data_path, 'aan/PKS_aanestysalueet_kkj2.TAB')
    ds = DataSource(path)
    kkj2 = SpatialReference('+proj=tmerc +lat_0=0 +lon_0=24 +k=1 +x_0=2500000 +y_0=0 +ellps=intl +towgs84=-96.0617,-82.4278,-121.7535,4.80107,0.34543,-1.37646,1.4964 +units=m +no_defs')
    kkj2_to_wgs84 = CoordTransform(kkj2, SpatialReference('WGS84'))
    lyr = ds[0]
    for feat in lyr:
        print feat.get('KUNTA')
        print feat.get('Nimi')
        feat.geom.srs = kkj2
        print feat
        geom = feat.geom
        geom.transform(kkj2_to_wgs84)
        print geom
        exit(1)
    print feat.fields
    exit(1)
"""

class Command(BaseCommand):
    help = "Manage stats app"

    def import_municipality_boundaries(self):
        path = os.path.join(self.data_path, 'TM_WORLD_BORDERS-0.3.shp')
        ds = DataSource(path)
        lyr = ds[0]
        for feat in lyr:
            if feat.get('ISO2') != 'FI':
                continue
            country_borders = feat.geom
            break

        path = os.path.join(self.data_path, 'SuomenKuntajako_2012_1000k.xml')
        ds = DataSource(path)
        lyr = ds[0]
        count = 0
        for feat in lyr:
            s = feat.get('LocalisedCharacterString')
            if not 'Kunta,Kommun' in s:
                continue
            s = feat.get('text')
            name = s.split(':')[1].split(',')[0]
            geom = feat.geom
            geom.transform(4326)

            # Take only the borders of the land mass
            intersect = geom.intersection(country_borders)
            # Some islands do not intersect country_borders.
            # Those we let be.
            if len(intersect):
                geom = intersect

            muni = Municipality.objects.get(name=name)
            try:
                mb = MunicipalityBoundary.objects.get(municipality=muni)
            except MunicipalityBoundary.DoesNotExist:
                mb = MunicipalityBoundary(municipality=muni)
                gm = GEOSGeometry(geom.wkb, srid=geom.srid)
                if not isinstance(gm, MultiPolygon):
                    gm = MultiPolygon(gm)
                mb.borders = gm
                mb.save()
                count += 1

        print "%d municipality boundaries added." % count

    def import_municipalities(self):
        s = self.http.open_url(MUNI_URL, "muni")
        # strip first 4 lines of header and any blank/empty lines at EOF
        count = 0
        for line in s.rstrip().split('\n')[4:]:
            dec_line = line.decode('iso8859-1').rstrip().split('\t')
            (muni_id, muni_name) = dec_line
            muni_id = int(muni_id)
            muni_name = muni_name.split(' - ')[0]

            try:
                muni = Municipality.objects.get(id=muni_id)
            except:
                muni = Municipality(id=muni_id, name=muni_name)
                muni.save()
                count += 1
        print "%d municipalities added." % count

    def import_elections(self):
        f = open(os.path.join(self.data_path, 'elections.txt'))
        count = 0
        for line in f.readlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            ar = line.split('\t')
            (el_year, el_type) = ar[0:2]
            el_date = ar[2]
            if len(ar) > 3:
                el_round = int(ar[3])
            else:
                el_round = 1
            try:
                el = Election.objects.get(year=el_year, type=el_type,
                                          round=el_round)
            except Election.DoesNotExist:
                el = Election(year=el_year, type=el_type, round=el_round,
                              date=el_date)
                count += 1
                el.save()
        print "%d elections added." % count

    def import_election_stats(self):
        election = Election.objects.get(year=2012, round=2, type="pres")
        try:
            statistic = Statistic.objects.get(slug="presidential-2012-round2")
        except Statistic.DoesNotExist:
            statistic = Statistic(name="Presidentinvaalit 2012 2. kierros",
                                  slug="presidential-2012-round",
                                  source="Tilastokeskus",
                                  source_url="http://pxweb2.stat.fi/Database/statfin/vaa/pvaa/pvaa_2012/pvaa_2012_fi.asp")
            statistic.save()

        f = open(os.path.join(self.data_path, 'Presidentti2012.csv'))
        count = 0
        for line in f.readlines()[1:]:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            ar = line.split('\t')
            muni = Municipality.objects.get(id=int(ar[1]))
            args = dict(election=election, municipality=muni, statistic=statistic)
            try:
                vp = VotingPercentage.objects.get(**args)
            except VotingPercentage.DoesNotExist:
                vp = VotingPercentage(**args)
                vp.value = ar[4]
                vp.save()
                count += 1
        print "%d voting percentage data points added." % count


    def handle(self, **options):
        http = HttpFetcher()
        http.set_cache_dir(os.path.join(settings.PROJECT_ROOT, ".cache"))
        self.data_path = os.path.join(settings.PROJECT_ROOT, '..', 'data')
        self.http = http
        self.import_municipalities()
        self.import_municipality_boundaries()
        self.import_elections()
        self.import_election_stats()
