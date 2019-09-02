from django.core.management.base import BaseCommand, CommandError
from phenotypedb.models import Study,RNASeq,RNASeqValue,Publication, Accession, Species, ObservationUnit, Submission

from django.db import transaction
import csv

def parse_rnacsv(rnaseq_csv):
    """parse a csv file and extract accessions and rnaseq names"""
    with open(rnaseq_csv, 'r') as f:
        reader = csv.reader(f)
        header = next(reader)[1:] # Skip the empty col
        # Generate dictionaries:
        rnavalues = {}
        for rna_id in header:
            rnavalues[rna_id] = []
        # Populate with entries
        accession_ids = []
        for line in reader:
            accession_ids.append(line[0])
            for i,rna_id in enumerate(header):
                rnavalues[rna_id].append(float(line[1+i]))
    return accession_ids, rnavalues

def parse_pubinfo(publication_file):
    """parse a file containing the publication information."""
    with open(publication_file, 'r') as f:
        # The parser splits lines using ': '
        publi_dict = dict()
        for line in f:
            cols = line[:-1].split(': ')
            fieldname = cols[0].lower()
            fieldname = ' '.join(fieldname.split(' ')) # remove trailing spaces
            publi_dict[cols[0].lower()] = cols[1]
    return publi_dict


@transaction.atomic
def save_rnaseq(accession_list, rnavalues, options):
    """save a csv file to db objects"""
    # Initialize Publication
    study = Study()
    study.name = options['study_name']
    study.species = Species.objects.get(pk=1)
    # Create a submission
    submission = Submission()
    submission.status = 2 # Published
    study.submission = submission
    study.save()
    # initialize publications
    print("Study created. Initializing publications.")
    if options['publication'] is not None:
        parsed_pub = parse_pubinfo(options['publication'])

        publication = Publication()
        try:
            publication.doi = parsed_pub['doi']
            publication.title = parsed_pub['title']
            publication.author_order = parsed_pub['publication author list']
            publication.pubmed_id = parsed_pub['pubmed id']
        except:
            print('Publication information could not be read, please include fields DOI, Title, Publication Author List, PubMed ID.')
        publication.save()
        study.publications.add(publication)

    # Create list of accessions
    obs_map = {}
    # Need to skip missing accessions
    skipped_sample_ids = []
    for sample_id, accession_id in enumerate(accession_list):
        accession_id = int(accession_id)
        try:
            obs_unit = ObservationUnit(study=study,accession=Accession.objects.get(pk=accession_id))
            obs_unit.save()
            obs_map[sample_id] = obs_unit
        except:
            print("Accession {} does not exist, skipping.".format(accession_id))
            skipped_sample_ids.append(sample_id)

    # Iterate through RNASeq measurements and save values
    print("There are {} RNA entries for each accessions.".format(len(rnavalues)))
    c = 0
    for rna_id in list(rnavalues.keys()):
        c+=1
        rnaseq = RNASeq(name=rna_id, scoring=options['scoring'],study=study,species=study.species)
        rnaseq.save()
        if c % 100 == 0:
            print("{} / {}".format(c, len(rnavalues)))
        for sample_id, value in enumerate(rnavalues[rna_id]):
            if sample_id in skipped_sample_ids:
                continue
            rnaseq_value = RNASeqValue(value=value, rnaseq=rnaseq, obs_unit = obs_map[sample_id])
            rnaseq_value.save()
    print("Successfully added RNASeq values for {} accessions across {} loci.".format(len(obs_map),len(rnavalues)))
    return study


class Command(BaseCommand):
    help = 'Import a csv file containing RNASeq results into the database'

    def add_arguments(self, parser):
        parser.add_argument('filename')
        parser.add_argument('--study_name',
                            type=str,
                            required=True,
                            help='Specify the name of the study')
        parser.add_argument('--publication',
                            type=str,
                            default=None,
                            required=False,
                            help='Specify the filename of the bibtex for the publication')
        parser.add_argument('--scoring',
                            type=str,
                            default='TPM',
                            required=False,
                            help='Specify the scoring system for the RNASeq assay')


    def handle(self, *args, **options):
        filename = options['filename']
        try:
            accession_list, rnavalues = parse_rnacsv(filename)
            print("RNASeq values loaded from file.")
            study = save_rnaseq(accession_list, rnavalues, options)
            study.save()
        except Exception as err:
            raise CommandError('Error importing CSV file. Reason: %s' % str(err))
        self.stdout.write(self.style.SUCCESS('Successfully imported CSV file "%s" under following id %s' % (filename,study)))