from django.test import TestCase, Client
from django.urls.base import reverse
from django.http import HttpResponseRedirect, HttpResponse
from analysis.models import Genes, Projects
from analysis.forms import AnalysisForm

# Create your tests here.
class YourTestCase(TestCase):
    def setUp(self):
        # This method is called before each test
        self.client = Client()
        for project in ['TCGA-BRCA', 'TCGA-BLCA', "TCGA-LAML"]:
            new = Projects(name=project)
            new.save()
        for gene in ['GATA1', 'ZEB1', 'TAP1']:
            new = Genes(name=gene)
            new.save()

    def test_bad_input(self):
        # BAD PROJECT ID
        bad_project = {'project': "fake",
               'gene_selected_1': 'GATA1', 
               'composite_analysis_type': "Single",
               'do_correlation_analysis': True}
        
        form = AnalysisForm()

        response = self.client.post(reverse('analysis-home'), data=bad_project)
        self.assertFormError(response, form, 'your_field', 'This field is required.')

        self.assertIsInstance(response, HttpResponse)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Genes ...', response.content)

        # BAD GENE INPUT
        bad_gene = {'project': "TCGA-BRCA",
            'gene_selected_1': 'fake', 
            'composite_analysis_type': "Single",
            'do_correlation_analysis': True}

        response = self.client.post(reverse('analysis-home'), data=bad_gene)
        self.assertIsInstance(response, HttpResponse)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Genes ...', response.content)

        # BAD COMPOSITE ANALYSIS TYPE
        bad_analysis = {'project': "TCGA-BRCA",
            'gene_selected_1': 'GATA1', 
            'composite_analysis_type': "fake",
            'do_correlation_analysis': True}

        response = self.client.post(reverse('analysis-home'), data=bad_analysis)
        self.assertIsInstance(response, HttpResponse)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Genes ...', response.content)


    """
    def test_post_request(self):
        #print(Projects.objects.all())
        #print(Projects.objects.filter(name='TCGA-BRCA'))
        # Define your POST data
        #bad_project = {'project': Projects.objects.filter(pk='TCGA-BRCA').first(),
        bad_project = {'project': "TCGA-BRCA",
                       'gene_selected_1': 'GATA1', 
                       'composite_analysis_type': "Single",
                       'do_correlation_analysis': True}

        #bad_composite_analysis_type = {'project': 'A fake project', 'key2': 'value2'}

        # Make a POST request using the client
        #response = self.client.post(reverse('analysis-home'), data=bad_project)
        #fetch

        response = self.client.post(reverse('analysis-home'), data=bad_project)

        # self.assertIsInstance(response, HttpResponseRedirect)
        self.assertIsInstance(response, HttpResponse)

        # Use assertRedirects to check for the redirection
        self.assertRedirects(response, reverse('analysis-fetch'), status_code=302)

        # You can also check for the target URL in the Location header
        # self.assertRedirects(response, reverse('analysis-home'), target_status_code=200)


        # Check the HTTP response status code
        content = response.content.decode('utf-8')
        #print(response.error)
        self.assertEqual(response.status_code, 200)  # Adjust the expected status code as needed

        # Check the content of the response
        content = response.content.decode('utf-8')  # Decode the bytes to a string
        #self.assertIn('Expected Text in Response', content)
    """