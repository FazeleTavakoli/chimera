import json
import re
import untangle
import xml.etree.ElementTree as ET
import  requests
import os

from utils.delex import Delexicalize
from data.WebNLG.rephrasing import rephrase, rephrase_if_must
from utils.graph import Graph
from utils.time import Time
from data.WebNLG.reader import WebNLGDataReader, RDFFileReader
from server import server
from model.model_runner import add_features
import xlsxwriter



class DataPreprocees:



    def readJsonFile(self):
        questionCounter = 0
        address_VQuAnDa_1 = "/Users/fazeletavakoli/PycharmProjects/chimera/VQuAnDa_1_0_train.json"
        with open(address_VQuAnDa_1, 'r') as jsonFile:
            dictionary = json.load(jsonFile)
        for entity in dictionary:
            subject_object_list = []
            # if questionCounter != 50:
            single_entity_dict = {}
            final_answer = ""
            question = entity['question']
            query = entity['query']
            found_triples = self.detect_regularExpression(query, "visualization")
            complexity = self.detect_complexity(query)
            verbalized_answer = entity['verbalized_answer']
            ### using 'SparqltoUser' webservice for getting interpretation of sparql query ###
            language = "en"
            # knowledgeBase = "wikidata"  # it doesn't work with "wikidata" when api is used not my local host.
            knowledgeBase = "dbpedia"
            # response = requests.get('https://qanswer-sparqltouser.univ-st-etienne.fr/sparqltouser',
            #                         params={'sparql':query, 'lang':language,'kb':knowledgeBase})  # this command also works without setting 'lang' and 'kb'
            response_s2u = requests.get('http://localhost:1920/sparqltouser',
                                    params={'sparql': query, 'lang': language, 'kb': knowledgeBase})
            jsonResponse = response_s2u.json()
            controlledLanguage = jsonResponse['interpretation']
            ##response from sparql endpoint(which is the answer of our question)
            response_se = requests.get('http://sda01dbpedia:softrock@131.220.9.219/sparql',
                                       params={'query': query})

            try:
                obj = untangle.parse(response_se.text)
            except:
                if response_se.text == "true":
                    final_answer = "true"
            if final_answer == "":  #if final_answer hasn't filled with "true" above
                try:
                    root = ET.fromstring(response_se.text)
                    if "COUNT" in query:
                        complete_answer = obj.sparql.results.result.binding.literal
                        final_answer = self.detect_regularExpression(str(complete_answer), "finalAnswer_number")
                    else:
                        if obj.sparql.results.result[0] == None:
                            complete_answer = obj.sparql.results.result.binding.uri
                            fianl_answer = self.detect_regularExpression(str(complete_answer), "finalAnswer_url")
                            final_answer = fianl_answer[1:]
                        else:
                            quantity_answers = len(obj.sparql.results.result)
                            if quantity_answers > 15:
                                max_range = 15
                            else:
                                max_range = quantity_answers
                            final_answer = "["  # in case of multiple answers, we want to have all of them in squared brackets
                            for i in range(0,max_range):
                                try:
                                    xml_root = root[1][i][0][0]
                                    result_middle = obj.sparql.results.result[i]
                                    # if result_middle.binding.get_attribute('uri') != None:
                                    if "uri" in str(xml_root):
                                        complete_answer = result_middle.binding.uri
                                        fianl_answer_i = self.detect_regularExpression(str(complete_answer), "finalAnswer_url")
                                        final_answer_i = fianl_answer_i[1:]
                                    else:
                                        complete_answer = result_middle.binding.literal
                                        final_answer_i = self.detect_regularExpression(str(complete_answer), "finalAnswer_number")
                                    final_answer = final_answer + final_answer_i + ", "
                                except:
                                    print("exception occured. Some answer is not included")
                                    continue
                            final_answer = final_answer[:len(final_answer)-2] #removing the last excessive comma
                            final_answer = final_answer + "]"
                except:
                    print("exception ocuured. Some questiopn is not included")
                    continue
            questionCounter = questionCounter + 1
            print(questionCounter)

            for i in range(0, len(found_triples)):
                for j in range(0, len(found_triples[i])):
                    if found_triples[i][j] == "?uri":
                        found_triples[i][j] = final_answer
                if (found_triples[i][0] not in (subject_object_list)) and (found_triples[i][0] != "?uri" and found_triples[i][0] != "?x"):
                    subject_object_list.append(found_triples[i][0])
                if found_triples[i][2] not in (subject_object_list) and (found_triples[i][2] != "?uri" and found_triples[i][2] != "?x"):
                    subject_object_list.append(found_triples[i][2])
            try:
                delexicalized_foramt = self.apply_delex(verbalized_answer, subject_object_list)
                text_plan = self.apply_exhaustive_plan(found_triples)
                text_plan_modified = add_features(text_plan)

                if type(delexicalized_foramt) == str and len(delexicalized_foramt) != 0 and len(text_plan) != 0:
                    self.write_into_file_txt("data/delex.txt", delexicalized_foramt) #writing delex into a file
                    self.write_into_file_txt("data/plan.txt", text_plan_modified) #writing plan into a file
                    self.write_into_file_txt("data/plan_no_text_feature.txt", text_plan)  # writing plan(without text feature) into a file
                else:
                    print("The result is not printed in the ouput file. Delixicalization is either non-string or empty, or plan is empty")


            except:
                print("exception occured. Some NMT module is causes the exception.")
                continue

    def detect_regularExpression(slef, inputString, purpose):
        if purpose == "visualization":
            # sparql_test = 'SELECT DISTINCT COUNT(?uri) WHERE { ?x <http://dbpedia.org/ontology/commander> <http://dbpedia.org/resource/Andrew_Jackson> . ?uri <http://dbpedia.org/ontology/knownFor> ?x  . }'
            lines = re.split('\s\.|\.\s', inputString)
            pattern = re.compile(
                r'(\?(uri))|(\?(x))|(resource/[^<>]+>)|(property/[^<>]+>)|(ontology/[^<>]+>)|(\#type)')  # lcquad_1
            nodes = []  # all entities u=including nodes and edges
            links = []
            nodes_and_links = []
            match_counter = 0
            contained_list = ["resource/", "property/", "ontology/"]
            for line in lines:
                if len(line) < 4:  # if the line is just made of a "}", at the end of the sparql query
                    break
                matches = pattern.finditer(line)
                current_nodes = []
                for match in matches:
                    contained_tag = 0
                    if match_counter != 0 or match.group() != "?uri":  # This if statement is just for preventing from entering this block
                        # when exactly the first match is "?uri". In some sparql queries we have ?uri before WHERE and in some other queries we don't.
                        for cl in contained_list:
                            contained_number = match.group().find(cl)
                            if contained_number != -1:
                                title = match.group()[contained_number + len(cl):]
                                contained_tag = 1
                                break
                        if contained_tag == 0:
                            title = match.group()
                        title = title.replace(">", "")
                        current_nodes.append(title)
                        if title not in nodes and current_nodes.index(title) != 1:
                            # if title not in nodes and not(('ontology/' in title and current_nodes.index(title) == 1)  or
                            #                               ('property/' in title or current_nodes.index(title) == 1) or
                            #                               '#type' in title):
                            nodes.append(title)
                    match_counter = match_counter + 1
                links.append([current_nodes[0], current_nodes[1], current_nodes[2]])
            # nodes_and_links.append(nodes)
            # nodes_and_links.append(links)
            return links
        elif purpose == "finalAnswer_url":
            pattern = re.compile(r'[/][^/]+')
            matches = pattern.finditer(inputString)
            for match in matches:
                title = match.group(0)  # changing the type of the title to String
            return title  # returns the last title
        elif purpose == "finalAnswer_number":
            pattern = re.compile(r'(cdata) ((\d+)|((\w+)(\s*))+)')
            matched_titles = pattern.finditer(inputString)
            for match in matched_titles:
                title = match.group(2)
            return title  # returns the last number, after cdata

    def detect_complexity(self, inputString):
        lines = re.split('\s\.|\.\s', inputString)
        question_complexity = 0  # it is calculated based on the number of sparql triples
        for line in lines:
            if len(line) < 4:
                break
            question_complexity = question_complexity + 1
        return question_complexity

    def write_into_file_json(self, path, input_object):
        # file = open(path, "a+")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(input_object, f, ensure_ascii=False, indent=4)

    def write_into_file_txt(self, path, input_string):
            with open(path, 'a+', encoding='utf-8') as f:
                f.write(input_string)
                f.write("\n")

    def remove_file_contents(self, path):
        if os.path.exists(path):
            with open(path, 'r+', encoding='utf-8') as f:
                f.read()
                f.seek(0)
                f.truncate(0)

    # this function generates a list of dictionaries, each contains a question, and an answer
    def QA_list_generator(self, question, answer, qa_list = []):
        qa_dict = {}
        qa_dict["question"] = question
        qa_dict["answer"] = answer
        qa_list.append(qa_dict)
        return qa_list

    def relexicalizer(self, delexicalized_file_path, relixicalized_file_path):
        with open(delexicalized_file_path, "r") as f:
            for line in f:
                words = re.split('\s|\.|\n', line)
                new_line = ""
                for word in words:
                    if "ENT_" in word:
                        word = word[4:len(word)-4]
                        word = word.replace("_", " ")
                        word = word.lower()
                    if "comma" in word:
                        word = word.replace(" comma ", ",")
                    new_line = new_line + word + " "
                new_line.strip()
                self.write_into_file_txt(relixicalized_file_path, new_line)


############################
# generating delex

    def apply_delex(self, text_format, entities_list):
        delex = Delexicalize(rephrase_f=rephrase, rephrase_if_must_f=rephrase_if_must)
        # examples = [
        #     ["There are [8] people known for works commanded by Andrew Jackson.", ['?x', 'commander', 'Andrew_Jackson']]
        #      ]
        delex_input = []
        text_entities_list = []
        text_entities_list.append(text_format)
        text_entities_list.append(entities_list)
        delex_input.append(text_entities_list)
        for sentence, entities in delex_input:
            # print("sentence is:", sentence)
            delex_run_result = delex.run(sentence, entities, True)
            # print("delex_run_result is: ", delex_run_result)
            # print("delex is:", delex)
            # print("closest_substring is:", delex.closest_substring(sentence, entities))
        return delex_run_result

############################
# generating plans
    def apply_exhaustive_plan(self, rdfs_list):
        # rdfs = [('William_Anders', 'dateOfRetirement', '"1969-09-01"'), ('William_Anders', 'birthPlace', 'British_Hong_Kong'),
        #             ('William_Anders', 'was a crew member of', 'Apollo_8')]
        rdfs_tuple_list = []
        for i in range(0, len(rdfs_list)):
            for j in range(0, len(rdfs_list[i])):
                rdf_tuple = (rdfs_list[i][0], rdfs_list[i][2], rdfs_list[i][1])
            rdfs_tuple_list.append(rdf_tuple)

        s = Graph(rdfs_tuple_list)

        # print("exhaustive")
        # now = Time.now()
        plans = s.exhaustive_plan().linearizations()
        # print(len(plans), "plans")
        # print(Time.passed(now))

        # now = Time.now()
        # print(len(plans), "plans")
        # print(Time.passed(now))
        return plans[0]
############################



if __name__ == '__main__':
    dp = DataPreprocees()
    # dp.remove_file_contents("data/delex.txt")
    # dp.remove_file_contents("data/plan.txt")
    # dp.remove_file_contents("data/plan_no_text_feature.txt")
    # dp.readJsonFile()
    dp.remove_file_contents("data/pred_relexicalized.txt")
    dp.relexicalizer("data/pred.txt", "data/pred_relexicalized.txt")






