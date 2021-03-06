# coding: utf-8
import pytest
import re

from click.testing import CliRunner

from oar.lib import db
from oar.cli.oarproperty import cli

#@pytest.yield_fixture(scope='function', autouse=True)
#def minimal_db_initialization(request):
#    with db.session(ephemeral=True):
#        yield

def test_version():
    runner = CliRunner()
    result = runner.invoke(cli, ['-V'])
    print(result.output)
    assert re.match(r'.*\d\.\d\.\d.*', result.output)

@pytest.mark.skipif("os.environ.get('DB_TYPE', '') != 'postgresql'", reason="need postgresql database") 
def test_oarproperty_add():
    runner = CliRunner()
    result = runner.invoke(cli, ['-a', 'fancy', '-c'])
    print(result.output)  
    assert result.exit_code == 0

@pytest.mark.skipif("os.environ.get('DB_TYPE', '') != 'postgresql'",
                    reason="need postgresql database")  
def test_oarproperty_simple_error():
    runner = CliRunner()
    
    result = runner.invoke(cli, ['-a core', '-c'])
    print(result.output)
    assert result.exit_code == 2

@pytest.mark.skipif("os.environ.get('DB_TYPE', '') != 'postgresql'", reason="need postgresql database") 
def test_oarproperty_add_error1():
    runner = CliRunner()
    result = runner.invoke(cli, ['-a', 'f#a:ncy'])
    print(result.output)
    assert re.match(r'.*is not a valid property name.*', result.output)
    assert result.exit_code == 0

@pytest.mark.skipif("os.environ.get('DB_TYPE', '') != 'postgresql'", reason="need postgresql database") 
def test_oarproperty_add_error2():
    runner = CliRunner()
    result = runner.invoke(cli, ['-a', 'state'])
    print(result.output)
    assert re.match(r'.*OAR system property.*', result.output)
    assert result.exit_code == 0

@pytest.mark.skipif("os.environ.get('DB_TYPE', '') != 'postgresql'", reason="need postgresql database") 
def test_oarproperty_add_error3():
    runner = CliRunner()
    result = runner.invoke(cli, ['-a', 'core'])
    print(result.output)
    assert re.match(r'.*already exists.*', result.output)
    
    assert result.exit_code == 0

@pytest.mark.skipif("os.environ.get('DB_TYPE', '') != 'postgresql'", reason="need postgresql database") 
def test_oarproperty_list():
    runner = CliRunner()
    result = runner.invoke(cli, ['--list'])
    print(result.output)
    assert result.output.split('\n')[0] == 'core'
    assert result.exit_code == 0


@pytest.mark.skipif("os.environ.get('DB_TYPE', '') != 'postgresql'",
                    reason="need postgresql database")
def test_oarproperty_delete():
    column_name1 = [p.name for p in db['resources'].columns]
    runner = CliRunner()
    result = runner.invoke(cli, ['-d','core'])
    print(result.output)
    column_name2 = [p.name for p in db['resources'].columns]
    #assert 'core' in db['resources'].columns
    assert result.exit_code == 0
    #assert len(column_name1) == len(column_name2) + 1
    kw = {"nullable": True}
    db.op.add_column('resources', db.Column('core', db.Integer, **kw))

@pytest.mark.skipif("os.environ.get('DB_TYPE', '') != 'postgresql'",
                    reason="need postgresql database")    
def test_oarproperty_rename():
    runner = CliRunner()
    result = runner.invoke(cli, ['--rename','core,eroc'])
    print(result.output)
    #assert 'eroc' in [p.name for p in db['resources'].columns]
    assert result.exit_code == 0
    db.op.alter_column('resources', 'eroc', new_column_name='core')
